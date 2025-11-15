from setuptools import setup, find_packages

NAME = "neo-api-client"
VERSION = "1.2.0"

REQUIRES = [
    'bidict>=0.22.1',
    'certifi>=2022.12.7',
    'idna>=3.4',
    'numpy>=1.24.2',
    'pyjsparser>=2.7.1',
    'PyJWT>=2.6.0',
    'python-dateutil>=2.8.2',
    'python-dotenv>=1.0.0',
    'requests>=2.31.0',
    'six>=1.16.0',
    'urllib3>=1.26.14',
    'websocket-client>=1.7.0',
    'websockets>=10.4',
    'pandas>=2.0.0',
    'pyotp>=2.9.0'
]

setup(
    name=NAME,
    version=VERSION,
    description="Neo Trade API Client for Kotak Securities",
    author="Kotak Neo Dev Team",
    author_email="support@kotaksecurities.com",
    url="https://github.com/Kotak-Neo/kotak-neo-api",
    keywords=["Neo Trade API", "Kotak Securities", "Neo API Client"],
    install_requires=REQUIRES,
    packages=find_packages(exclude=["test", "tests"]),
    include_package_data=True,
    long_description="""\
    Official Python client to access the Kotak Neo Trade APIs.
    Supports authentication, session handling, and market data retrieval.
    """
)
