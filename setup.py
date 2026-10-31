# pyproject.toml is the source of truth; this copy of the metadata keeps old pip/setuptools
# (e.g. the pip 21 bundled with macOS's Python 3.9) installing correctly. Keep the two in sync.
from setuptools import setup, find_packages

setup(
    name="visor-browser",
    version="0.2.0",
    description="Self-healing browser automation that reads the screen: click, fill and verify by visible text.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={"visor": ["strategy/tree.json"]},
    install_requires=[
        "playwright>=1.39.0",
        "opencv-python>=4.8.0",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
        "rich>=13.0.0",
        "ocrmac>=1.0.0; sys_platform == 'darwin'",
        "easyocr>=1.7.1; sys_platform != 'darwin'",
    ],
    extras_require={
        "easyocr": ["easyocr>=1.7.1"],
        "mac": ["ocrmac>=1.0.0"],
        "agent": ["anthropic>=2.3; python_version >= '3.10'"],
        "dev": ["pytest>=7.4.0"]
    },
    entry_points={
        "console_scripts": [
            "visor=visor.cli:main",
        ]
    },
    python_requires=">=3.9",
)
