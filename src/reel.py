"""하이쿠 릴스(세로 9:16 mp4)를 만든다. 이미 만든 포스터 5장을 이어 붙이므로 AI 호출이 없다(토큰 0).

  python -m src.reel out/h004          out/h004/ 안의 01~05 jpg로 reel.mp4 만들기 (연습용)
필요: ffmpeg (GitHub Actions 워크플로가 설치함)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

RW, RH = 1080, 1920
DURATIONS = [2.6, 3.2, 3.8, 4.2, 2.8]   # 슬라이드별 보여 줄 시간(초) — 합계 약 16초에서 겹침 제외
FADE = 0.4


def _canvas(src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGB")
    bg = tuple(int(v) for v in np.median(np.asarray(im).reshape(-1, 3), axis=0))  # 포스터 바탕색
    c = Image.new("RGB", (RW, RH), bg)
    c.paste(im, ((RW - im.width) // 2, (RH - im.height) // 2))
    c.save(dst, quality=92)


def make_reel(images: list[Path], out: Path, durations: list[float] | None = None) -> Path:
    durs = (durations or DURATIONS)[: len(images)]
    with tempfile.TemporaryDirectory() as td:
        frames = []
        for i, p in enumerate(images):
            f = Path(td) / f"f{i}.jpg"
            _canvas(Path(p), f)
            frames.append(f)
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for f, d in zip(frames, durs):
            cmd += ["-loop", "1", "-framerate", "30", "-t", f"{d + FADE:.2f}", "-i", str(f)]
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        chain, off, last = [], 0.0, "[0:v]"
        for k in range(1, len(frames)):
            off += durs[k - 1] - FADE
            tag = f"[x{k}]"
            chain.append(f"{last}[{k}:v]xfade=transition=fade:duration={FADE}:offset={off:.2f}{tag}")
            last = tag
        total = sum(durs) - FADE * (len(frames) - 1)
        if not chain:
            chain, last = ["[0:v]null[x0]"], "[x0]"
        cmd += ["-filter_complex", ";".join(chain), "-map", last, "-map", f"{len(frames)}:a",
                "-t", f"{total:.2f}", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"ffmpeg 실패: {r.stderr[-600:]}")
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    imgs = sorted(d.glob("[0-9][0-9]*.jpg"))
    print(make_reel(imgs, d / "reel.mp4"))
