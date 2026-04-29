from pathlib import Path


def test_backend_dockerfile_installs_weasyprint_native_runtime_dependencies() -> None:
    dockerfile = Path("Dockerfile").read_text()
    required_packages = {
        "fonts-dejavu-core",
        "libgdk-pixbuf-2.0-0",
        "libpango-1.0-0",
        "libpangoft2-1.0-0",
        "shared-mime-info",
    }

    missing = sorted(package for package in required_packages if package not in dockerfile)
    assert not missing, f"Dockerfile missing native PDF runtime dependencies: {missing}"
