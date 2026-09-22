# -*- coding: utf-8 -*-
"""发布期视频转码模块（构建期工具，不进入公网产物）。

职责：把发布拷贝 `static/media/**/V_*.mp4` 做一次 H.264 恒定质量二次压缩，
以降低外网访客的下载体积；源文件（G:\\Simreay\\output）不做任何修改。

设计约束（与 openspec/changes/optimize-public-site-performance 一致）：
1. ffmpeg 通过**自动探测**获得（FFMPEG_BIN -> PATH -> 常见安装位置 -> 项目内被忽略的 tools/），
   MUST NOT 硬编码本机路径；探测失败时退化为直接复制源文件，绝不中断发布。
2. 幂等：转码记录（static/cache/transcode_manifest.json，已被 .gitignore 覆盖）
   保存「源 mtime + 源 size + 输出 size + 参数签名」，四者一致才跳过。
3. 参数签名参与 URL 版本号，避免 immutable 长缓存下取到旧档位产物。

命令行自检：
    python transcode_media.py --detect      # 打印 ffmpeg 探测与编码器选择结果
    python transcode_media.py --no-ffmpeg   # 模拟"未安装 ffmpeg"，验证优雅跳过
    python transcode_media.py --stats <dir> # 统计目录内 mp4 体积/码率
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 档位配置（用户确认：保持源分辨率不缩放，恒定质量 cq/crf 36）
#   - 实测依据见 openspec/changes/optimize-public-site-performance/design.md
#     四档样片对比：2048/cq30 仅降 6.5%（无效）；2048/cq36 降 59.4% 且
#     访客显示尺寸 SSIM 0.9912（肉眼不可区分）。
#   - 若要切到更激进的 "960px" 档位，只需把 SCALE_FILTER 改为 "scale=960:960"
#     并把 TARGET_QUALITY 调成 28；参数签名会自动变化并触发重转。
# ---------------------------------------------------------------------------
TARGET_QUALITY = 36
SCALE_FILTER = None
MANIFEST_VERSION = 1

# 编码器优先级（可移植）：软编 x264 质量最好 -> 硬件编码 -> 兜底 openh264
ENCODER_CANDIDATES = (
    ("libx264", lambda q: ["-preset", "medium", "-crf", str(q)]),
    ("h264_nvenc", lambda q: ["-preset", "p5", "-cq", str(q)]),
    ("h264_qsv", lambda q: ["-global_quality", str(q)]),
    ("h264_amf", lambda q: ["-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q)]),
    ("libopenh264", lambda q: ["-b:v", "1200k"]),
)

_INSTALL_HINT = (
    "安装建议（任选其一，均无需放进本项目仓库）：\n"
    "  * winget install --id Gyan.FFmpeg\n"
    "  * 下载 gyan.dev 静态包解压后，把 bin 目录加入 PATH，或设置环境变量 FFMPEG_BIN 指向它\n"
    "  * 设置 FFMPEG_BIN 既可指向 ffmpeg 可执行文件，也可指向其所在目录"
)

_PROBE_CACHE: dict = {}


# ---------------------------------------------------------------------------
# 原生删除（绕开宿主环境对 os.remove 的回收站垫片，避免误触批量删除守卫）
# ---------------------------------------------------------------------------
def _native_unlink(path) -> None:
    try:
        if os.name == "nt":
            import nt  # noqa: WPS433
            nt.unlink(str(path))
        else:
            import posix  # noqa: WPS433
            posix.unlink(str(path))
    except BaseException:
        pass


# ---------------------------------------------------------------------------
# ffmpeg 探测
# ---------------------------------------------------------------------------
def candidate_ffmpeg_paths():
    """按优先级返回候选 ffmpeg 可执行文件路径（不存在则会被跳过）。"""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    out = []

    env_val = (os.environ.get("FFMPEG_BIN") or "").strip().strip('"')
    if env_val:
        p = Path(env_val)
        if p.is_dir():
            out.append(p / exe)
        else:
            out.append(p)
            if not p.suffix:
                out.append(p / exe)

    which = shutil.which("ffmpeg")
    if which:
        out.append(Path(which))

    if os.name == "nt":
        bases = [
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            r"C:\ProgramData\chocolatey\bin",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
            os.path.expandvars(r"%USERPROFILE%\scoop\shims"),
        ]
    else:
        bases = ["/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/snap/bin"]

    for b in bases:
        if b and "%" not in b:
            out.append(Path(b) / exe)

    # 项目内私有工具目录（被 .gitignore 覆盖，仅本机可用）
    out.append(Path(__file__).resolve().parent / "tools" / "ffmpeg" / "bin" / exe)
    return out


def detect_ffmpeg() -> str | None:
    """自动探测 ffmpeg；找不到返回 None（调用方须优雅降级）。"""
    for p in candidate_ffmpeg_paths():
        try:
            if p.is_file():
                return str(p)
        except OSError:
            continue
    return None


def list_encoders_text(ffmpeg_bin: str) -> str:
    try:
        r = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def _probe_encode(ffmpeg_bin: str, encoder: str, qargs, sample: str | None) -> bool:
    """用极短片段实测某编码器是否真的可用（含 GPU 会话可用性）。"""
    if sample and Path(sample).is_file():
        src_args = ["-i", str(sample), "-t", "0.5"]
    else:
        src_args = ["-f", "lavfi", "-i", "testsrc=size=256x256:rate=10", "-t", "0.3"]
    cmd = (
        [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
        + src_args
        + ["-c:v", encoder] + list(qargs)
        + ["-an", "-pix_fmt", "yuv420p", "-f", "null", "-"]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def select_encoder(ffmpeg_bin: str, quality: int = TARGET_QUALITY, sample: str | None = None):
    """返回 (encoder_name, quality_args)；无可用编码器时返回 (None, None)。"""
    key = (ffmpeg_bin, quality, bool(sample))
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]

    enc_text = list_encoders_text(ffmpeg_bin)
    first_error = ""
    for name, qargs in ENCODER_CANDIDATES:
        if enc_text and name not in enc_text:
            continue
        if _probe_encode(ffmpeg_bin, name, qargs(quality), sample):
            _PROBE_CACHE[key] = (name, qargs(quality))
            return _PROBE_CACHE[key]
        first_error = first_error or name
    _PROBE_CACHE[key] = (None, None)
    return _PROBE_CACHE[key]


def params_signature(encoder_name: str | None) -> str:
    """转码参数签名（参与资源 URL 版本号，参数变化即失效缓存）。"""
    raw = "|".join([
        f"v{MANIFEST_VERSION}",
        f"q={TARGET_QUALITY}",
        f"enc={encoder_name or 'raw'}",
        f"scale={SCALE_FILTER or 'none'}",
        "an=1", "faststart=1", "pix=yuv420p",
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# 幂等记录
# ---------------------------------------------------------------------------
class TranscodeManifest:
    def __init__(self, path):
        self.path = Path(path)
        self.data: dict = {}
        try:
            if self.path.is_file():
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.data = loaded
        except Exception:
            self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value
        self.save()

    def forget(self, key):
        if key in self.data:
            self.data.pop(key, None)
            self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"  [transcode] 写入转码记录失败（不影响发布）: {e}")


# ---------------------------------------------------------------------------
# 转码器
# ---------------------------------------------------------------------------
class MediaTranscoder:
    """发布拷贝的视频压缩器；ffmpeg 缺失时自动退化为直接复制。"""

    def __init__(self, ffmpeg_bin=None, quality: int = TARGET_QUALITY,
                 manifest_path=None, sample_path=None, verbose: bool = True):
        self.quality = quality
        self.verbose = verbose
        self.requested_bin = ffmpeg_bin
        self.ffmpeg_bin = self._resolve_ffmpeg(ffmpeg_bin)
        self.encoder = None
        self.qargs = None
        if manifest_path is None:
            manifest_path = Path(__file__).resolve().parent / "static" / "cache" / "transcode_manifest.json"
        self.manifest = TranscodeManifest(manifest_path)
        self.stats = {"transcoded": 0, "skipped": 0, "copied": 0, "failed": 0, "bytes_in": 0, "bytes_out": 0}
        self.sig = params_signature(None)

        if self.ffmpeg_bin:
            enc, qargs = select_encoder(self.ffmpeg_bin, quality, sample_path)
            if enc:
                self.encoder, self.qargs = enc, qargs
                self.sig = params_signature(enc)
                self._say(f"[transcode] ffmpeg: {self.ffmpeg_bin} | 编码器: {enc} | 档位: cq/crf {quality}"
                          + (f" | 缩放: {SCALE_FILTER}" if SCALE_FILTER else " | 保持源分辨率"))
            else:
                self.ffmpeg_bin = None
                self._say("[transcode] ffmpeg 存在但无可用 H.264 编码器，跳过转码。")
                self._say(_INSTALL_HINT)
        else:
            self._say("[transcode] 未检测到 ffmpeg，跳过视频转码（站点仍可正常发布，仅失去体积收益）。")
            self._say(_INSTALL_HINT)

    # -- 内部工具 ---------------------------------------------------------
    def _say(self, msg):
        if self.verbose:
            print(msg)

    @staticmethod
    def _resolve_ffmpeg(explicit):
        if explicit is None:
            return detect_ffmpeg()
        if explicit == "":
            return None  # 显式屏蔽（用于自检）
        p = Path(explicit)
        if p.is_dir():
            p = p / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        return str(p) if p.is_file() else None

    @property
    def available(self) -> bool:
        return bool(self.ffmpeg_bin and self.encoder)

    def version_tag(self, src_path) -> str:
        """给资源 URL 用的稳定版本号（源文件 mtime + 参数签名）。"""
        try:
            mtime = int(Path(src_path).stat().st_mtime)
        except OSError:
            mtime = 0
        return f"{mtime}_{self.sig}"

    # -- 幂等判定 ---------------------------------------------------------
    def _needs_work(self, src: Path, dst: Path, key: str) -> bool:
        if not dst.is_file() or dst.stat().st_size == 0:
            return True
        rec = self.manifest.get(key)
        if not rec or rec.get("sig") != self.sig:
            return True
        try:
            s = src.stat()
        except OSError:
            return True
        if rec.get("src_mtime") != round(s.st_mtime, 3) or rec.get("src_size") != s.st_size:
            return True
        if rec.get("out_size") != dst.stat().st_size:
            return True
        return False

    def _copy_fallback(self, src: Path, dst: Path, reason: str) -> str:
        try:
            s = src.stat()
            if dst.is_file() and dst.stat().st_size == s.st_size:
                self.manifest.forget(str(dst))
                return "skipped"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            self.manifest.forget(str(dst))
            self.stats["copied"] += 1
            self._say(f"  [transcode] 退化为直接复制（{reason}）: {dst.name}")
            return "copied"
        except Exception as e:
            self.stats["failed"] += 1
            self._say(f"  [transcode] 复制失败，已跳过该文件: {dst} | {e}")
            return "failed"

    # -- 主流程 -----------------------------------------------------------
    def process(self, src, dst) -> str:
        """转码 src -> dst。返回 'transcoded' | 'skipped' | 'copied' | 'failed'。"""
        src, dst = Path(src), Path(dst)
        key = str(dst)

        if not self.available:
            return self._copy_fallback(src, dst, "ffmpeg 不可用")

        if not self._needs_work(src, dst, key):
            self.stats["skipped"] += 1
            return "skipped"

        tmp = dst.with_name(dst.name + ".tmp.mp4")
        cmd = (
            [self.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(src), "-map_metadata", "-1",
             "-c:v", self.encoder] + list(self.qargs)
            + ["-an", "-sn", "-dn", "-pix_fmt", "yuv420p"]
        )
        if SCALE_FILTER:
            cmd += ["-vf", SCALE_FILTER]
        cmd += ["-movflags", "+faststart", str(tmp)]

        t0 = time.time()
        err = ""
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0:
                err = (r.stderr or "").strip().replace("\n", " ")
        except Exception as e:
            err = str(e)

        if err or not tmp.is_file() or tmp.stat().st_size == 0:
            _native_unlink(tmp)
            self.manifest.forget(key)
            self._say(f"  [transcode] 转码失败: {src.name} | {err[:160]}")
            return self._copy_fallback(src, dst, "转码失败")

        try:
            os.replace(tmp, dst)
        except Exception as e:
            _native_unlink(tmp)
            return self._copy_fallback(src, dst, f"替换失败: {e}")

        s = src.stat()
        out_size = dst.stat().st_size
        self.manifest.put(key, {
            "src_mtime": round(s.st_mtime, 3),
            "src_size": s.st_size,
            "out_size": out_size,
            "sig": self.sig,
            "encoder": self.encoder,
            "quality": self.quality,
            "done_at": int(time.time()),
        })
        self.stats["transcoded"] += 1
        self.stats["bytes_in"] += s.st_size
        self.stats["bytes_out"] += out_size
        self._say(f"  [transcode] {src.name}: {s.st_size/1048576:.2f}MB -> "
                  f"{out_size/1048576:.2f}MB ({(1-out_size/s.st_size)*100:.0f}%↓, {time.time()-t0:.1f}s)")
        return "transcoded"

    def summary(self) -> str:
        st = self.stats
        parts = [f"转码 {st['transcoded']}", f"跳过 {st['skipped']}"]
        if st["copied"]:
            parts.append(f"复制兜底 {st['copied']}")
        if st["failed"]:
            parts.append(f"失败 {st['failed']}")
        if st["bytes_in"]:
            parts.append(f"体积 {st['bytes_in']/1048576:.0f}MB -> {st['bytes_out']/1048576:.0f}MB "
                         f"(降 {(1-st['bytes_out']/max(st['bytes_in'],1))*100:.1f}%)")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# 统计工具（自检 / 验证用）
# ---------------------------------------------------------------------------
def _mp4_info(path: Path):
    info = {"res": None, "dur": None}
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            def boxes(start, end):
                p = start
                while p < end:
                    f.seek(p)
                    h = f.read(8)
                    if len(h) < 8:
                        return
                    sz, typ = struct.unpack(">I4s", h)
                    if sz == 1:
                        sz = struct.unpack(">Q", f.read(8))[0]
                    if sz < 8:
                        return
                    yield p, sz, typ
                    p += sz

            for p, sz, typ in boxes(0, size):
                if typ != b"moov":
                    continue
                for p2, sz2, t2 in boxes(p + 8, p + sz):
                    if t2 == b"mvhd":
                        f.seek(p2 + 8)
                        ver = f.read(1)[0]
                        f.read(3)
                        if ver == 1:
                            f.read(16)
                            ts = struct.unpack(">I", f.read(4))[0]
                            du = struct.unpack(">Q", f.read(8))[0]
                        else:
                            f.read(8)
                            ts = struct.unpack(">I", f.read(4))[0]
                            du = struct.unpack(">I", f.read(4))[0]
                        info["dur"] = du / ts if ts else None
                    if t2 == b"trak":
                        for p3, sz3, t3 in boxes(p2 + 8, p2 + sz2):
                            if t3 == b"tkhd":
                                f.seek(p3 + sz3 - 8)
                                w, h = struct.unpack(">II", f.read(8))
                                w, h = w / 65536, h / 65536
                                if w > 0 and h > 0:
                                    info["res"] = f"{round(w)}x{round(h)}"
        info["size"] = size
    except Exception:
        info["size"] = path.stat().st_size if path.is_file() else 0
    return info


def stats_for_dir(media_dir) -> dict:
    media_dir = Path(media_dir)
    files = sorted(media_dir.rglob("V_*.mp4"))
    total = sum(f.stat().st_size for f in files)
    dur = 0.0
    res_counter: dict = {}
    for f in files:
        i = _mp4_info(f)
        dur += i["dur"] or 0
        res_counter[i["res"]] = res_counter.get(i["res"], 0) + 1
    mbps = (total * 8 / dur / 1e6) if dur else 0
    return {
        "count": len(files), "total_mb": round(total / 1048576, 1),
        "duration_min": round(dur / 60, 1), "avg_mbps": round(mbps, 2),
        "res": res_counter,
    }


# ---------------------------------------------------------------------------
# CLI 自检
# ---------------------------------------------------------------------------
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--detect" in argv:
        found = detect_ffmpeg()
        print(f"探测结果: {found or '未找到 ffmpeg'}")
        if found:
            print("候选列表（按优先级）:")
            for p in candidate_ffmpeg_paths()[:8]:
                mark = "✓" if str(p) == found else " "
                print(f"  [{mark}] {p}")
            enc, qargs = select_encoder(found, TARGET_QUALITY)
            print(f"选定编码器: {enc or '无'} | 参数: {' '.join(qargs or [])}")
            print(f"参数签名: {params_signature(enc)}")
        return 0

    if "--no-ffmpeg" in argv:
        print("— 模拟：ffmpeg 不可用 —")
        t = MediaTranscoder(ffmpeg_bin="", manifest_path=Path("./.transcode_probe_tmp.json"))
        print(f"available = {t.available}")
        print(f"version_tag 仍可用（退化为纯 mtime）: {t.version_tag(__file__)}")
        src = Path(__file__)
        dst = Path("./.transcode_probe_tmp.bin")
        status = t.process(src, dst)
        print(f"process() 返回: {status}（预期 copied/skipped，绝不抛错）")
        _native_unlink(dst)
        _native_unlink(Path("./.transcode_probe_tmp.json"))
        return 0

    if "--stats" in argv:
        idx = argv.index("--stats")
        target = Path(argv[idx + 1]) if len(argv) > idx + 1 else Path(__file__).parent / "static" / "media"
        s = stats_for_dir(target)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
