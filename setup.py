from setuptools import setup, find_packages

setup(
    name="holo1",
    version="0.1.0",
    description="Web browsing agent with Playwright and vision-language model integration.",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "playwright>=1.52.0",
        "transformers>=4.52.4",
        "torch>=2.7.0",
        "pillow>=11.2.1",
        # Add other dependencies from req.txt/requrements.txt as needed
    ],
    python_requires=">=3.8",
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "holo1=holo1.main:main"
        ]
    },
    url="https://github.com/yourusername/holo1",  # Update with your repo
    license="MIT",  # Or your chosen license
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
)