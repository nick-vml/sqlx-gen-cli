from setuptools import setup, find_packages

setup(
    name="sqlx_gen",
    version="1.1.2",
    description="Framework de geração automática de SQLX para Dataform/BigQuery",
    author="VML",
    packages=find_packages(include=["src", "src.*"]),
    py_modules=["main"],
    install_requires=[
        "typer>=0.12.0",
        "rich>=13.0.0",
        "jinja2>=3.1.0",
        "pyarrow>=14.0.0",
        "gcsfs>=2023.10.0",
        "pyyaml>=6.0.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "openai>=1.0.0",
        "pyfiglet>=1.0.2"
    ],
    entry_points={
        "console_scripts": [
            "sqlx_gen=main:app",
        ],
    },
    python_requires=">=3.9",
)
