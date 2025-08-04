from setuptools import setup, find_packages

setup(
    name='liteInstru',
    version='0.1.0',
    packages=find_packages(),
    install_requires=['numpy','matplotlib','pyvisa','qcodes','scipy','xarray','tomlkit'],
    author='shiau109, RatisWu',
    author_email='porkface0301@gmail.com',
    description='Extensions for LiteVNA',
    url='https://github.com/shiau109/LiteVNA',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
    ],
)
