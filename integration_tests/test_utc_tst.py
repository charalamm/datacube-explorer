"""
Tests that load pages and check the contained text.
"""
from pathlib import Path

import pytest
from datacube.index.hl import Doc2Dataset
from datacube.utils import read_documents
from flask.testing import FlaskClient

from datacube.model import Range
from datetime import datetime
from dateutil import tz
from cubedash.summary import SummaryStore

from integration_tests.asserts import check_dataset_count, get_html

TEST_DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture(scope="module", autouse=True)
def populate_index(dataset_loader, module_dea_index):
    """
    Index populated with example datasets. Assumes our tests wont modify the data!

    It's module-scoped as it's expensive to populate.
    """
    dataset_count = 0
    create_dataset = Doc2Dataset(module_dea_index)
    for _, s2_dataset_doc in read_documents(TEST_DATA_DIR / "ls5_fc_albers-sample.yaml"):
        try:
            dataset, err = create_dataset(
                s2_dataset_doc, "file://example.com/test_dataset/"
            )
            assert dataset is not None, err
            created = module_dea_index.datasets.add(dataset)
            assert created.type.name == "ls5_fc_albers"
            dataset_count += 1
        except AttributeError as ae:
            assert dataset_count == 5
            print(ae)
    assert dataset_count == 5
    return module_dea_index


def test_summary_product(client: FlaskClient):
    # These datasets have gigantic footprints that can trip up postgis.
    html = get_html(client, "/ls5_fc_albers")

    check_dataset_count(html, 5)


def test_yearly_dataset_count(client: FlaskClient):
    html = get_html(client, "/ls5_fc_albers/2010/12")
    check_dataset_count(html, 2)

    html = get_html(client, "/ls5_fc_albers/2010/12/31")
    check_dataset_count(html, 2)

    html = get_html(client, "/ls5_fc_albers/2011")
    check_dataset_count(html, 3)


def test_dataset_search_page_localised_time(client: FlaskClient):
    html = get_html(client, "/products/ls5_fc_albers/datasets/2011")

    assert (
        "2011-01-01 09:03:13" in [
            a.find("td", first=True).text.strip() for a in html.find(".search-result")
        ]
    ), "datestring does not match expected center_time recorded in dataset_spatial table"

    assert (
        "Time UTC: 2010-12-31 23:33:13" in [
            a.find("td", first=True).attrs["title"] for a in html.find(".search-result")
        ]
    ), "datestring does not match expected center_time recorded in dataset_spatial table"

    html = get_html(client, "/products/ls5_fc_albers/datasets/2010")

    assert (
        "2010-12-31 09:56:02" in [
            a.find("td", first=True).text.strip() for a in html.find(".search-result")
        ]
    ), "datestring does not match expected center_time recorded in dataset_spatial table"


def test_clirunner_generate_grouping_timezone(module_dea_index, run_generate):
    res: Result = run_generate("ls5_fc_albers", grouping_time_zone="America/Chicago")
    assert "2010" in res.output

    store = SummaryStore.create(module_dea_index, grouping_time_zone="America/Chicago")


    # simulate search pages
    datasets = sorted(
        store.index.datasets.search(**{
            'product': 'ls5_fc_albers',
            'time': Range(
                begin=datetime(
                    2010, 12, 30, 0, 0,
                    tzinfo=tz.gettz("America/Chicago")
                ),
                end=datetime(
                    2010, 12, 31, 0, 0,
                    tzinfo=tz.gettz("America/Chicago")
                )
            )
        }, limit =5),
        key=lambda d: d.center_time,
    )
    assert len(datasets) == 2

    # search pages
    datasets = sorted(
        store.index.datasets.search(**{
            'product': 'ls5_fc_albers',
            'time': Range(
                begin=datetime(
                    2010, 12, 31, 0, 0,
                    tzinfo=tz.gettz("America/Chicago")
                ),
                end=datetime(
                    2011, 1, 1, 0, 0,
                    tzinfo=tz.gettz("America/Chicago")
                )
            )
        }, limit =5),
        key=lambda d: d.center_time,
    )
    assert len(datasets) == 3

    # simulate product pages
    result = store.get("ls5_fc_albers", year=2010, month=12)
    assert result.dataset_count == 5

    result = store.get("ls5_fc_albers", year=2010, month=12, day=30)
    assert result.dataset_count == 2

    result = store.get("ls5_fc_albers", year=2010, month=12, day=31)
    assert result.dataset_count == 3
