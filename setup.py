"""Project configuration for packaging and installation."""

from pathlib import Path
from typing import List

from setuptools import find_packages, setup

BASE_DIR = Path(__file__).resolve().parent


def get_requirements() -> List[str]:
    """Return project dependencies from requirements.txt."""
    requirements_path = BASE_DIR / "requirements.txt"
    if not requirements_path.exists():
        print("requirements.txt file not found")
        return []

    requirements: List[str] = []
    with requirements_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            requirement = raw_line.strip()
            if requirement and not requirement.startswith("#") and requirement != "-e .":
                requirements.append(requirement)

    return requirements


if __name__ == "__main__":
    setup(
        name="networksecurity",
        version="0.1.0",
        description="Network security project for phishing data",
        packages=find_packages(),
        include_package_data=True,
        install_requires=get_requirements(),
    )

