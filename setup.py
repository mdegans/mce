import os

import setuptools

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(THIS_DIR, 'README.md')) as readme:
    long_description = readme.read()

setuptools.setup(
    name='mce',
    version='0.1.3',
    description='Mechanical Compound Eye',
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',

        # 'Topic :: Software Development :: Build Tools',
        # todo; find appropriate topic

        # todo: figure out license
        # 'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    python_requires='>=3.6',
    # install_requires=['requests'],
    packages=['mce'],
    package_data={
        'mce': [
            'pie.conf',
        ]
    },
    entry_points={
        'console_scripts': ['mce=mce.__main__:cli_main'],
    },
    author='Michael de Gans',
    author_email='michael.john.degans@gmail.com',
    project_urls={
        'Bug Reports': 'https://github.com/mdegans/mce/issues',
        'Source': 'https://github.com/mdegans/mce/',
    },
)
