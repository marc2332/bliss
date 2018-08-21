Developer\'s Guide
==================

The BLISS project is hosted on the [ESRF Gitlab](https://gitlab.esrf.fr/bliss/bliss).

Cloning
-------

To clone bliss:

    $ git clone git@gitlab.esrf.fr:bliss/bliss.git

The first thing to do after cloning bliss is to set up the pre-commit hook:

    $ ./pre-commit.sh
    pre-commit installed at /home/user/bliss/.git/hooks/pre-commit

This will cause black to run before any commit is made, ensuring a consistent
code style in the project. For more information, see the
[code formatting](dev_guidelines.md#code-formatting) section.


Bliss has some dependencies on third-party software. The complete list
of dependencies can be obtained from the `setup.py` script:

    $ python setup.py egg_info

(see `bliss.egg_info/requirements.txt`).

Your work environment is a matter of taste. If you want to isolate your
bliss development it is a good idea to use virtualenv or Conda.

Workflow
--------

Bliss project promotes a development based on [Feature Branch
Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow):

> The core idea behind the [Feature Branch
> Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow)
> is that all feature development should take place in a dedicated
> branch instead of the master branch. This encapsulation makes it easy
> for multiple developers to work on a particular feature without
> disturbing the main codebase. It also means **the master branch will
> never contain broken code**, which is a huge advantage for continuous
> integration environments.
>
> Encapsulating feature development also makes it possible to leverage
> pull requests, which are a way to initiate discussions around a
> branch. They give other developers the opportunity to sign off on a
> feature before it gets integrated into the official project. Or, if
> you get stuck in the middle of a feature, you can open a pull request
> asking for suggestions from your colleagues. The point is, pull
> requests make it incredibly easy for your team to comment on each
> other's work.

### Use case story 1: Adding a new controller

John has been asked by beamline ID00 to integrate a new pressure meter
from Alibaba Inc, in their experiments.

-   First, he checks the [\~bliss.controllers]{role="mod"} repository to
    see if the device is already implemented
-   If not, he creates a new
    [issue](http://gitlab.esrf.fr/bliss/bliss/issues/new?issue) on
    gitlab. He assigns it to himself and adds labels *new feature* and
    *plugin*. He is very happy to receive a comment by his colleague
    Maria that happened to receive a similar request from ID99. They
    quickly agree on a shared development
-   They both agree to work on a new branch called
    *alibaba\_pressure\_meter*. Since John is going on vacation, it is
    up to poor Maria to start developing
-   She clones the Bliss repository and creates a new branch
    called *alibaba\_pressure\_meter*:

        $ git checkout -b alibaba_pressure_meter

-   She is a fan of [TDD]{role="term"}, so she starts thinking how she
    would like to control the device and then she starts writing simple
    unit tests. They will all fail in the beginning but that doesn\'t
    scare her at all because now she knows exactly what to do to make
    them work
-   After some development, Maria is happy with the result so she pushes
    her work to gitlab. She can immediately see on the Bliss [ESRF
    Gitlab]() project page a new log entry with the work she just
    pushed. Gitlab even offers to create a *merge request* so she just
    clicks on it, fills in the missing data in the form and assigns her
    colleague Marco to integrate her merge request. Maria is quite
    confident because she knows that an extra pair of eyes will help
    catch any issue with her proposition
-   Marco makes some comments on Maria\'s code directly on the gitlab
    merge request web page. Maria realizes that she forgot to document
    one of the most important methods so she fixes the commit. Marco can
    now accept the merge request
-   John comes back from vacation and he is suprised to see the code for
    his device is already available in the master branch. Since his use
    case is a little different that Maria\'s, he realizes that he needs
    to add a couple more functions so he makes a new
    [issue](http://gitlab.esrf.fr/bliss/bliss/issues/new?issue) on
    gitlab and the process repeats again

Contributing
------------

You can contribute to Bliss in many ways: from simple (or hard) bug
fixes to writting new controller extensions, introduce new features or
writing documentation. No matter how you are contributing, the following
principles apply:

-   Try to use the same code style as used in the rest of the project.
    See the [bliss-style-guide]{role="ref"} below for more information
-   New features should be documented. Include examples and use cases
    where appropriate
-   Add appropriate unit tests



Bliss Style Guide
-----------------

The Bliss style guide summarizes the Bliss coding guidelines. When
adding code to Bliss (new feature, new extension or simply a patch) make
sure you follow these guide lines.

In general the Bliss Style Guide closely follows [PEP8](https://www.python.org/dev/peps/pep-0008/) with
some small differences and extensions.


Code formatting
---------------

Code formatting is automatically managed by [black](https://black.readthedocs.io/en/stable/).

There is 3 complementary ways to work with black:

- [Integrate it in your editor](https://black.readthedocs.io/en/stable/editor_integration.html)
  (Emacs, Vim, etc.)

- Run it using the command line interface:

        $ pip3 install black
		[...]
        $ black .
        All done! ✨ 🍰 ✨
        466 files left unchanged.

- Let the pre-commit hook format your changes. Make sure it is properly set up by running:

        $ ./pre-commit

      **Note:** If black changed any of the staged code during the pre-commit phase, the commit
	  will abort. This lets you check the changes black made before re-applying the commit:

	  ```bash
	  $ git commit demo.py -m "Some message"
      black..........................................................Failed
      Files were modified by this hook. Additional output:
      reformatted doc/demo.py
      All done! ✨ 🍰 ✨
      1 file reformatted.
      [WARNING] Stashed changes conflicted with hook auto-fixes...
	  Rolling back fixes...
      $ git commit demo.py -m "Some message"
      black..........................................................Passed
      [branch 89b740f2] Some message
      1 file changed, 1 insertion(+)
      ```

Naming Conventions
------------------

-   Module names: `lowercase_with_underscores`
-   Class names: `CamelCase`, with acronyms kept uppercase (`HTTPWriter`
    and not `HttpWriter`)
-   Variable names: `lowercase_with_underscores`
-   Method and function names: `lowercase_with_underscores`
-   Constants: `UPPERCASE_WITH_UNDERSCORES`
-   precompiled regular expressions: `name_re`

Protected members are prefixed with a single underscore. Double
underscores are reserved for mixin classes.

On classes with keywords, trailing underscores are appended. Clashes
with builtins are allowed and **must not** be resolved by appending an
underline to the variable name. If the function needs to access a
shadowed builtin, rebind the builtin to a different name instead.

Function and method arguments:

:   -   class methods: `cls` as first parameter
    -   instance methods: `self` as first parameter
    -   lambdas for properties might have the first parameter replaced
        with `x` like in
        `display_name = property(lambda x: x.real_name or x.username)`


Docstrings convention
---------------------

All docstrings are formatted with reStructuredText as understood by
Sphinx. Depending on the number of lines in the docstring, they are
laid out differently. If it\'s just one line, the closing triple
quote is on the same line as the opening, otherwise the text is on
the same line as the opening quote and the triple quote that closes
the string on its own line:

```python

    def foo():
        """This is a simple docstring"""


    def bar():
        """
        This is a longer docstring with so much information in there
        that it spans three lines.  In this case the closing triple quote
        is on its own line.
        """
```

Bliss supports *napoleon* sphinx extension. The recommended way to
document API is to follow the [Google Python Style
Guide](http://google.github.io/styleguide/pyguide.html):

``` python
    def move(axis, position, wait=False):
		"""
		move the given axis to the given absolute position

		Note:
			using `wait=True` will block the current :class:`~gevent.Greenlet`.

	    See Also:
			:func:`rmove`

	    Args:
			axis (Axis): instance of bliss :class:`bliss.common.axis.Axis`
			position (float): position (axis units)
			wait (bool): wait or not for motion to end [default: False]

        Returns:
			float: actual position where motor is (axis units)
		"""
		pass
```


Comments
--------

Rules for comments are similar to docstrings. Both are formatted with
reStructuredText. If a comment is used to document an attribute, put a
colon after the opening pound sign (`#`):

    class User(object):

        #: the name of the user as unicode string
        name = Column(String)

        #: the sha1 hash of the password + inline salt
        pw_hash = Column(String)


Bliss Module Template
---------------------

Here is a template that you can use to start writing a new bliss module:

```python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""A brief description goes here.

Long description here with examples if possible
"""

__all__ = [] # list of members to export

# standard module imports

# third-party module imports

# local bliss imports
```

Example of a motor controller extension:

~~~python
# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2016 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""ExampleController motor controller

To instantiate a new ExampleController motor controller, configure it with:

```yaml
    plugin: emotion
    class: ExampleController
    host: iceid00a
    axes:
      - name: th
        address: 01
        unit: deg
        steps_per_unit: 1
        velocity: 0        # unit/s
        acceleration: 0    # unit/s/s
        backlash:          # unit
```

"""

__all__ = ['ExampleController']

import os
import sys
import string

import gevent

from bliss.controllers.motor import Controller

class ExampleController(Controller):
    """
    The ExampleController motor controller.
    """

    def move(self, axis, position, wait=False):
        """
        Move the given axis to the given absolute position

        Note:
            using `wait=True` will block the current :class:`~gevent.Greenlet`.

        See Also:
            :meth:`~ExampleController.rmove`

        Args:
            axis (int): valid axis number (1..8, 11..18, ...,)
            position (int): position (steps)
            wait (bool): wait or not for motion to end [default: False]

        Returns:
            int: actual position where motor is (steps)
        """
        pass

~~~
