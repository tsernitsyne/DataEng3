import argparse
import os
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--data", default="data", type=Path)
    args = parser.parse_args()

    data_dir = args.data.resolve()
    disks = [data_dir / f"vol{number}" for number in range(1, 5)]
    for disk in disks:
        disk.mkdir(parents=True, exist_ok=True)

    addresses = []
    for number, disk in enumerate(disks):
        port = 9110 + 10 * number
        disk_path = disk.as_posix()
        if os.name == "nt":
            disk_path = "/%3F/" + disk_path
        addresses.append(f"http://127.0.0.1:{port}/{disk_path}")

    environment = os.environ.copy()
    environment["RUSTFS_ACCESS_KEY"] = environment["AWS_ACCESS_KEY_ID"]
    environment["RUSTFS_SECRET_KEY"] = environment["AWS_SECRET_ACCESS_KEY"]
    environment["RUSTFS_STORAGE_CLASS_STANDARD"] = "EC:2"
    environment["RUSTFS_UNSAFE_BYPASS_DISK_CHECK"] = "true"

    servers = []
    logs = []
    try:
        for number in range(4):
            port = 9110 + 10 * number
            environment["RUSTFS_OBS_LOG_DIRECTORY"] = str(data_dir / f"logs{number + 1}")
            stdout = (data_dir / f"node{number + 1}.stdout.log").open("w")
            stderr = (data_dir / f"node{number + 1}.stderr.log").open("w")
            logs.extend((stdout, stderr))
            servers.append(subprocess.Popen(
                [
                    str(args.binary.resolve()),
                    "server",
                    "--address",
                    f"127.0.0.1:{port}",
                    "--console-enable",
                    "--console-address",
                    f"127.0.0.1:{port + 1}",
                    *addresses,
                ],
                env=environment,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ))

        print("RustFS processes:", [server.pid for server in servers], flush=True)
        while all(server.poll() is None for server in servers):
            time.sleep(2)
        raise RuntimeError("A RustFS process stopped; inspect data/node*.stderr.log")
    finally:
        for server in servers:
            if server.poll() is None:
                server.terminate()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
