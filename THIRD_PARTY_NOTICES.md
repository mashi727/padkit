# Third-party notices

## padtools_ts

`src/padkit/_vendor/padtools_ts/` contains the built `dist/`, `package.json`,
`package-lock.json`, `README.md` and the SPD grammar (`spd.langium`) of
[steelpipe75/padtools_ts](https://github.com/steelpipe75/padtools_ts),
pinned to the commit recorded in `PIN.json`. It is redistributed under the MIT
License; the full text is in `src/padkit/_vendor/padtools_ts/LICENSE`
(Copyright (c) 2025 steelpipe).

Its npm dependencies are not vendored. `padkit setup` installs them with
`npm ci` from the pinned `package-lock.json`; each package carries its own license.
