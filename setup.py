from setuptools import setup, find_packages

setup(
    name="visor",
    version="0.1.0",
    description="A self-healing, human-in-the-loop browser automation framework.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "playwright>=1.39.0",
        "easyocr>=1.7.1",
        "Pillow>=10.0.0",
        "opencv-python>=4.8.0",
        "rich>=13.0.0"
    ],
    extras_require={
        "dev": ["pytest>=7.4.0"]
    },
    entry_points={
        "console_scripts": [
            "visor=visor.cli:main",
        ]
    },
    python_requires=">=3.9",
)
