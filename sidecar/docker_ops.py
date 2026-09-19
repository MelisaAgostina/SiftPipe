import os
import subprocess


def _compose_base_cmd(compose_files: list[str]) -> list[str]:
    cmd = ["docker", "compose"]
    for f in compose_files:
        cmd += ["-f", f]
    return cmd


def compose_down_services(repo_root: str, compose_files: list[str], services: list[str]) -> None:
    cmd = _compose_base_cmd(compose_files) + ["rm", "-f", "-s", "-v"] + services
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def compose_up_services(repo_root: str, compose_files: list[str], services: list[str]) -> None:
    cmd = _compose_base_cmd(compose_files) + ["up", "-d"] + services
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def compose_restart_service(repo_root: str, compose_files: list[str], service: str) -> None:
    cmd = _compose_base_cmd(compose_files) + ["restart", service]
    subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)


def wipe_host_dir(host_path: str) -> None:
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{host_path}:/target",
        "alpine:3.20",
        "sh", "-c", "rm -rf /target/* /target/..?* /target/.[!.]* 2>/dev/null; true",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def delete_host_file(host_path: str) -> None:
    # Bind-mounting the file itself and rm-ing that exact path fails with
    # EBUSY (can't unlink an active mount point) — mount the parent dir
    # instead and delete by basename.
    parent_dir = os.path.dirname(host_path)
    filename = os.path.basename(host_path)
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{parent_dir}:/target",
        "alpine:3.20",
        "sh", "-c", f"rm -f /target/{filename}",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
