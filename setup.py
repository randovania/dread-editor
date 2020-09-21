from setuptools import setup, find_packages

with open("README.md") as readme_file:
    long_description = readme_file.read()

setup(
    name='retro-memory-viewer',
    author='Henrique Gemignani',
    url='https://github.com/henriquegemignani/retro-memory-viewer',
    description='A realtime memory viewer for the randomizer for the Metroid Prime 2: Echoes.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    scripts=[
    ],
    package_data={
    },
    license='License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Games/Entertainment',
    ],
    python_requires=">=3.7",
    setup_requires=[
    ],
    install_requires=[
        'dolphin-memory-engine>=1.0.2',
        'imgui[pygame]',
    ],
    extras_require={
    },
    entry_points={
    },
)
