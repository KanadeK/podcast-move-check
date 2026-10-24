# Third-party software and provenance

Runtime dependencies: Python (provided by the user under the PSF license), and
[defusedxml 0.7.1](https://github.com/tiran/defusedxml) by Christian Heimes, distributed
separately under the Python Software Foundation license (PSFL). Its upstream license
and copyright remain in the installed dependency; no dependency source is copied
into this repository. Its permissive terms are compatible with our MIT project code.

Development tools are installed separately: setuptools (MIT), build (MIT), Ruff (MIT).
GitHub Actions checkout and setup-python are MIT-licensed services/actions referenced
by immutable commit IDs. They are not included in the distributed Python package.

All project source and synthetic fixtures in this repository were written for this project.
External specifications and competing projects are linked as references, not copied
implementations. The MIT license applies to our code and fixtures, not linked material.
