"""Docker-only real execution; no generated code runs on the host."""
import asyncio
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.config import settings


class SandboxRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50_000)
    timeout: float = Field(default=15, gt=0, le=30)


class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    is_mock: bool = False


async def capture_bounded(stream, limit=16_384):
    kept = bytearray()
    while chunk := await stream.read(4096):
        kept.extend(chunk[:max(0, limit - len(kept))])
    return kept.decode("utf-8", errors="replace")


class DockerAdapter:
    async def execute(self, request: SandboxRequest) -> SandboxResult:
        name = "speed-" + uuid4().hex
        process = None
        readers = []
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm", "--pull=never", "--name", name,
                "--network=none", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--user=65534:65534",
                "--memory=128m", "--cpus=0.5", "--pids-limit=32",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "--workdir=/tmp", "-i",
                settings.speed_sandbox_image, "python", "-I", "-",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            readers = [asyncio.create_task(capture_bounded(process.stdout)),
                       asyncio.create_task(capture_bounded(process.stderr))]
            timed_out = False
            try:
                async with asyncio.timeout(request.timeout):
                    process.stdin.write(request.code.encode())
                    await process.stdin.drain()
                    process.stdin.close()
                    await process.wait()
                    stdout, stderr = await asyncio.gather(*readers)
            except TimeoutError:
                timed_out = True
                if process.returncode is None:
                    process.kill()
                await process.wait()
                stdout, stderr = "", "Execution timed out"
            return SandboxResult(stdout=stdout, stderr=stderr,
                                 exit_code=124 if timed_out else process.returncode,
                                 timed_out=timed_out)
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            # Killing the CLI alone does not guarantee container cleanup.
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", name, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(cleanup.wait(), 5)
                except TimeoutError:
                    cleanup.kill()
                    await cleanup.wait()
            finally:
                for reader in readers:
                    if not reader.done():
                        reader.cancel()
                await asyncio.gather(*readers, return_exceptions=True)


class SandboxRuntime:
    def __init__(self, adapter=None, mode=None):
        self.adapter = adapter or DockerAdapter()
        self.mode = mode or settings.speed_sandbox_mode

    async def execute(self, inputs, trace):
        request = SandboxRequest.model_validate(inputs)
        mock = self.mode == "mock"
        trace.emit("sandbox.started", "Sandbox: python calculation", "running", is_mock=mock)
        try:
            if self.mode == "disabled":
                raise RuntimeError("Sandbox is disabled")
            if mock:
                result = SandboxResult(stdout="MOCK: example execution only; code was not run.",
                                       stderr="", exit_code=0, is_mock=True)
            else:
                result = await self.adapter.execute(request)
            for channel in ("stdout", "stderr"):
                output = getattr(result, channel)
                if output:
                    trace.emit(f"sandbox.{channel}", f"Captured {channel}", is_mock=result.is_mock,
                               summary=f"{len(output.encode())} bytes; content private")
            trace.emit("sandbox.failed" if result.exit_code else "sandbox.completed",
                       f"Sandbox exit {result.exit_code}", "failed" if result.exit_code else "completed",
                       is_mock=result.is_mock, metadata={"exit_code": result.exit_code,
                       "timed_out": result.timed_out, "stdout_bytes": len(result.stdout.encode()),
                       "stderr_bytes": len(result.stderr.encode())})
            if result.exit_code:
                raise SandboxFailure("Sandbox did not complete successfully")
            return result.model_dump()
        except SandboxFailure:
            raise
        except Exception:
            trace.emit("sandbox.failed", "Sandbox unavailable or execution failed", "failed", is_mock=mock)
            raise


class SandboxFailure(RuntimeError):
    pass
