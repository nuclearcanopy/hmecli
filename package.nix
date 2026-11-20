{
  lib,
  python3Packages,
  xdg-utils,
}:
python3Packages.buildPythonApplication {
  pname = "hmecli";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    root = ./.;
    fileset = lib.fileset.unions [
      ./hmecli.py
      ./test_hmecli.py
      ./pyproject.toml
      ./README.md
    ];
  };

  build-system = [ python3Packages.setuptools ];
  dependencies = [ python3Packages.browser-cookie3 ];

  # `login` opens the browser via webbrowser -> xdg-open
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [ xdg-utils ])
  ];

  nativeCheckInputs = [ python3Packages.unittestCheckHook ];
  pythonImportsCheck = [ "hmecli" ];

  meta = {
    description = "Generate iCloud Hide My Email aliases from the command line";
    homepage = "https://github.com/nuclearcanopy/hmecli";
    license = lib.licenses.mit;
    mainProgram = "hmecli";
    platforms = lib.platforms.linux;
  };
}
