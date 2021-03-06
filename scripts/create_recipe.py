import yaml
import subprocess
import os
import sys
import re

try:
    import conda.cli.python_api as conda
    from conda.cli import main_info
    from conda_env.cli import main_export
except ModuleNotFoundError:
    pass


CURDIR = os.path.dirname(os.path.abspath(__file__))
BLISS_DIR = os.path.dirname(CURDIR)
sys.path.append(BLISS_DIR)

from setup import console_script_entry_points

META = os.path.join(CURDIR, "meta.yaml")

if sys.platform in ["win32", "cygwin"]:
    REQ_PATH = os.path.join(BLISS_DIR, "requirements-win64.txt")
else:
    REQ_PATH = os.path.join(BLISS_DIR, "requirements.txt")

# regex
conda_pack_regex = re.compile(
    r"(.*)==(.*)=(.*)"
)  # to understand conda package versions
pip_pack_regex = re.compile(r"(.*)==(.*)")  # to understand pip package versions


def is_tagged(tag=None):
    """
    Returns:
        True if current commit has a git tag
        False if not
    """
    tagged_version = r"^(\d+\.){2,3}(\d+)$"
    if not tag:
        output = subprocess.run(["git", "describe", "--tag"], capture_output=True)
        stdout = output.stdout.decode().strip()
    else:
        stdout = tag
    m = re.match(tagged_version, stdout)
    if m:
        return True
    return False


def get_git_tag(tag=None):
    """
    Gives information about current tag, it manages tags with 2, 3 or 4 numbers
    including tags containing rc in the last one
    ES: 0.2, 1.3rc0, 1.2.10, 1.2.3.3, 1.2.3rc2

    Returns:
        list with version specs if current commit has a tag
        list with version specs + number of commits since last tag + hash

    Example:
        (0, 23, 1)  on a tagged commit
        (0, 23, 0rc1)  on a tagged commit
        (0, 0, 101, 12, g34189fd6) on an untagged commit
    """
    tagged_version_2 = r"(\d+)\.((?:\d+)(?:(?:rc)?(?:\d))?)$"
    tagged_version_3 = r"(\d+)\." + tagged_version_2
    tagged_version_4 = r"(\d+)\." + tagged_version_3
    derived_version_2 = r"(\d+)\.(\d+)-(\d+)-([a-z0-9]+)$"
    derived_version_3 = r"(\d+)\." + derived_version_2
    derived_version_4 = r"(\d+)\." + derived_version_3
    if not tag:
        output = subprocess.run(["git", "describe", "--tag"], capture_output=True)
        if output.returncode:
            raise Exception("Can't execute subprocess git describe --tag")
        stdout = output.stdout.decode().strip()
    else:
        stdout = tag
    for regx in (
        tagged_version_2,
        tagged_version_3,
        tagged_version_4,
        derived_version_2,
        derived_version_3,
        derived_version_4,
    ):
        m = re.match(regx, stdout)
        if m:
            return list(m.groups())


def find_conda_package(search_string):
    """
    Search for a conda package
    Returns:
        True if Found, False if not found
    """
    output = subprocess.run(
        ["conda", "search", f"{search_string}"], capture_output=True
    )
    if output.returncode:
        return False
    return True


def dependencies_pip():
    """
    Returns:
        list: pip dependencies in tuple form (name, version)
    """
    # current environment info
    conda_current_env_info = main_info.get_info_dict()
    # current installed dependencies
    dependencies = main_export.from_environment(
        "bliss", conda_current_env_info["conda_prefix"]
    ).dependencies
    name_version = dict()
    for dep in dependencies.get("pip", list()):
        match = pip_pack_regex.match(dep)
        if match:
            name, version = match.groups()
            name_version[name] = version
    return name_version


def dependencies_conda():
    """
    Returns:
        list: conda dependencies in tuple form (name, version)
    """
    # current environment info
    conda_current_env_info = main_info.get_info_dict()
    # current installed dependencies
    dependencies = main_export.from_environment(
        "bliss", conda_current_env_info["conda_prefix"]
    ).dependencies
    name_version = dict()
    for dep in dependencies.get("conda", list()):
        match = conda_pack_regex.match(dep)
        if match:
            name, version, build = match.groups()
            name_version[name] = version
    return name_version


def conda_requirements_txt(path):
    """
    Extracts conda requirements from text file
    """
    conda_req_file = []
    with open(path) as f:
        for line in f:
            if len(line.strip()):  # remove blank lines
                name = line.split()[0]
                if name != "#":  # remove comments
                    conda_req_file.append(name)
    return conda_req_file


def main():

    template_head = f"""
    package:
      name: bliss
    source:
      #git_url: https://gitlab.esrf.fr/bliss/bliss.git
      path: {BLISS_DIR}
    """

    template_body = """
    build:
      number: 0
      script: python -m pip install --no-deps .

    requirements:
      build:
              - python
              - setuptools
              - pip
              - cython
              - silx
    about:
      home: https://gitlab.esrf.fr/bliss/bliss
      license: LGPL License
      summary: 'The BLISS experiments control system'
      license_family: GPL
    """

    head = yaml.load(template_head)
    body = yaml.load(template_body)

    print("Git tag version", get_git_tag())

    head["package"]["version"] = ".".join(get_git_tag())
    head["source"]["git_rev"] = ".".join(get_git_tag())

    # console script entry points
    body["build"]["entry_points"] = list()
    for entry_point in console_script_entry_points:
        body["build"]["entry_points"].append(entry_point)

    # conda current environment
    body["requirements"]["run"] = list()

    # matching between requirements.txt and
    # current installed version of packages

    # populating a dictionary with installed packages
    conda_req_current_env = dependencies_conda()

    # reading requirements.txt to get only package names
    # versions will be taken from current environment
    conda_req_file = conda_requirements_txt(REQ_PATH)

    # populating meta.yaml with names and versions

    for name, version in dependencies_pip().items():
        if find_conda_package(f"{name}=={version}"):
            print(f"Found pip dependency on conda for {name}=={version}")
        else:
            print(f"Not found pip dependency on conda for {name}=={version}")

    # finding dependencies
    for name in conda_req_file:
        if name in conda_req_current_env:
            version = conda_req_current_env[name]
            body["requirements"]["run"].append(f"{name} {version}")
        else:
            body["requirements"]["run"].append(name + " # missing conda package")

    # writing meta.yaml
    with open(META, "w") as f:
        f.write(yaml.dump(head, default_flow_style=False))
        f.write(yaml.dump(body, default_flow_style=False))


if __name__ == "__main__":
    main()
