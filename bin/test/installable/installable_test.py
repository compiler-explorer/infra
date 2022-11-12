from unittest.mock import MagicMock

import pytest

from lib.installable.installable import Installable
from lib.installation_context import InstallationContext


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return MagicMock(spec=InstallationContext)


def test_installable_sort(fake_context):
    ab_c = Installable(fake_context, dict(context=["a", "b"], name="c"))
    v1_2_3 = Installable(fake_context, dict(context=[], name="1.2.3"))
    v10_1 = Installable(fake_context, dict(context=[], name="10.1"))
    v10_1_alpha = Installable(fake_context, dict(context=[], name="10.1-alpha"))
    v10_2 = Installable(fake_context, dict(context=[], name="10.2"))
    assert sorted([v10_1, v10_1_alpha, ab_c, v1_2_3, v10_2], key=lambda x: x.sort_key) == [
        v1_2_3,
        v10_1,
        v10_1_alpha,
        v10_2,
        ab_c,
    ]
