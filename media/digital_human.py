from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import httpx

from utils.config import get_settings
from utils.logger import log


@dataclass
class DigitalHumanResult:
    video_path: str
    duration: float
    engine: str


class DigitalHumanEngine(ABC):
    @abstractmethod
    def generate(self, audio_path: str, output_path: str) -> DigitalHumanResult:
        ...


class HeyGemEngine(DigitalHumanEngine):
    """Integration with HeyGem local API for digital human video generation.

    HeyGem API flow:
    1. POST /api/v1/video/create - submit task with audio + reference video
    2. GET /api/v1/video/status/{task_id} - poll task status
    3. GET /api/v1/video/download/{task_id} - download result
    """

    def __init__(self):
        settings = get_settings()
        dh_cfg = settings["digital_human"]
        self.api_url = dh_cfg["api_url"].rstrip("/")
        self.reference_video = dh_cfg.get("reference_video", "./assets/avatar.mp4")
        self.resolution = dh_cfg.get("resolution", "1080x1920")
        self.timeout = 600
        self.poll_interval = 5

    def generate(self, audio_path: str, output_path: str) -> DigitalHumanResult:
        log.info(f"HeyGem: generating digital human video from {audio_path}")

        task_id = self._create_task(audio_path)
        log.info(f"HeyGem: task created: {task_id}")

        self._wait_for_completion(task_id)
        self._download_result(task_id, output_path)

        duration = self._get_video_duration(output_path)
        log.info(f"HeyGem: video generated at {output_path} ({duration:.1f}s)")

        return DigitalHumanResult(
            video_path=output_path,
            duration=duration,
            engine="heygem",
        )

    def _create_task(self, audio_path: str) -> str:
        with open(audio_path, "rb") as af:
            files = {"audio": af}
            if Path(self.reference_video).exists():
                with open(self.reference_video, "rb") as vf:
                    files["reference_video"] = vf
                    resp = httpx.post(
                        f"{self.api_url}/api/v1/video/create",
                        files=files,
                        data={"resolution": self.resolution},
                        timeout=60,
                    )
            else:
                resp = httpx.post(
                    f"{self.api_url}/api/v1/video/create",
                    files=files,
                    data={"resolution": self.resolution},
                    timeout=60,
                )

        resp.raise_for_status()
        return resp.json()["task_id"]

    def _wait_for_completion(self, task_id: str):
        start = time.time()
        while time.time() - start < self.timeout:
            resp = httpx.get(
                f"{self.api_url}/api/v1/video/status/{task_id}",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")

            if status == "completed":
                return
            elif status == "failed":
                raise RuntimeError(f"HeyGem task failed: {data.get('error', 'unknown')}")

            log.info(f"HeyGem: task {task_id} status={status}, progress={data.get('progress', '?')}%")
            time.sleep(self.poll_interval)

        raise TimeoutError(f"HeyGem task {task_id} timed out after {self.timeout}s")

    def _download_result(self, task_id: str, output_path: str):
        with httpx.stream(
            "GET",
            f"{self.api_url}/api/v1/video/download/{task_id}",
            timeout=120,
        ) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    @staticmethod
    def _get_video_duration(path: str) -> float:
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0


class PassthroughEngine(DigitalHumanEngine):
    """Fallback engine: skip digital human, produce a static-image video from audio.

    Useful when HeyGem is not available. Creates a simple video with a static
    background image and the audio track, using FFmpeg.
    """

    def __init__(self):
        settings = get_settings()
        self.resolution = settings["digital_human"].get("resolution", "1080x1920")

    def generate(self, audio_path: str, output_path: str) -> DigitalHumanResult:
        import subprocess
        log.info(f"Passthrough: generating static video from {audio_path}")

        w, h = self.resolution.split("x")
        bg_path = Path(__file__).parent.parent / "assets" / "background.png"

        if bg_path.exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(bg_path),
                "-i", audio_path,
                "-c:v", "libx264", "-tune", "stillimage",
                "-c:a", "aac", "-b:a", "192k",
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
                "-shortest", "-pix_fmt", "yuv420p",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={w}x{h}:d=300",
                "-i", audio_path,
                "-c:v", "libx264",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-pix_fmt", "yuv420p",
                output_path,
            ]

        subprocess.run(cmd, capture_output=True, timeout=120, check=True)

        duration = HeyGemEngine._get_video_duration(output_path)
        log.info(f"Passthrough: static video generated at {output_path} ({duration:.1f}s)")

        return DigitalHumanResult(
            video_path=output_path,
            duration=duration,
            engine="passthrough",
        )


def create_digital_human_engine() -> DigitalHumanEngine:
    settings = get_settings()
    engine_name = settings["digital_human"].get("engine", "heygem")

    if engine_name == "heygem":
        try:
            resp = httpx.get(
                f"{settings['digital_human']['api_url']}/api/v1/health",
                timeout=5,
            )
            if resp.status_code == 200:
                log.info("Using HeyGem digital human engine")
                return HeyGemEngine()
        except Exception:
            log.warning("HeyGem not available, falling back to passthrough engine")

    log.info("Using passthrough (static image) engine")
    return PassthroughEngine()
