"""Makes this directory a package, which is the whole content of this file.

Without it pytest names a test module by its basename alone and puts *this*
directory on `sys.path`. Two consequences, both of which only appear once
`uv sync --extra browser` has been run, since the directory is skipped whole
without it:

* `tests/browser/test_graph.py` and `tests/test_graph.py` are both the module
  `test_graph`, and collection fails with an import file mismatch;
* `from conftest import FakeAnki` in three top-level tests resolves to the
  conftest *here*, because this directory is inserted first.

So the documented way to run these tests broke the rest of the suite. As a
package the modules are `browser.test_graph`, `tests/` goes on the path
instead, and both problems are gone.
"""
