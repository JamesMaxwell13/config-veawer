from setuptools import find_packages, setup

setup(
    name="netbox-config-weaver",
    version="0.2.0",
    description="Plugin for managing network device configurations in NetBox",
    install_requires=[
        "PyYAML>=6.0",
        "netmiko>=4.3.0",
        "paramiko>=3.4.0",
        "cryptography>=43.0.0",
        "channels>=4.1.0",
        "daphne>=4.1.0",
    ],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
)
