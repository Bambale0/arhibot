from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, UnidentifiedImageError

_RENDER_TIMEOUT_SECONDS = 300


class BlenderRendererError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BlenderRenderResult:
    data: bytes
    width: int
    height: int
    renderer_version: str


class BlenderRenderer:
    """Run the versioned canonical preview profile in a separate Blender process."""

    def __init__(self, executable: str = "blender") -> None:
        self.executable = executable
        self.script_path = Path(__file__).with_name("blender_entrypoint.py")

    async def version(self) -> str:
        process = await asyncio.create_subprocess_exec(
            self.executable,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=20)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BlenderRendererError("Blender version check timed out.") from exc
        if process.returncode != 0:
            raise BlenderRendererError(
                f"Blender version check failed with exit code {process.returncode}."
            )
        first_line = stdout.decode("utf-8", errors="replace").splitlines()[0].strip()
        if not first_line.lower().startswith("blender"):
            raise BlenderRendererError("Unexpected Blender version output.")
        return first_line[:120]

    async def render(self, glb_data: bytes) -> BlenderRenderResult:
        renderer_version = await self.version()
        with TemporaryDirectory(prefix="auroom-blender-") as temp_dir:
            temp = Path(temp_dir)
            input_path = temp / "canonical.glb"
            output_path = temp / "hero.png"
            await asyncio.to_thread(input_path.write_bytes, glb_data)

            process = await asyncio.create_subprocess_exec(
                self.executable,
                "--background",
                "--factory-startup",
                "--python",
                str(self.script_path),
                "--",
                str(input_path),
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(), timeout=_RENDER_TIMEOUT_SECONDS
                )
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise BlenderRendererError("Blender render exceeded the safety timeout.") from exc

            log_tail = stdout.decode("utf-8", errors="replace")[-4000:]
            if process.returncode != 0:
                raise BlenderRendererError(
                    f"Blender render failed with exit code {process.returncode}: {log_tail}"
                )
            if not output_path.is_file():
                raise BlenderRendererError("Blender completed without producing the PNG output.")

            data = await asyncio.to_thread(output_path.read_bytes)
            try:
                with Image.open(BytesIO(data)) as image:
                    image.verify()
                with Image.open(BytesIO(data)) as image:
                    width, height = image.size
                    image_format = image.format
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise BlenderRendererError("Blender produced an invalid image.") from exc
            if image_format != "PNG" or width <= 0 or height <= 0:
                raise BlenderRendererError("Blender output must be a non-empty PNG image.")
            return BlenderRenderResult(
                data=data,
                width=width,
                height=height,
                renderer_version=renderer_version,
            )
