"""Preprocessing of raw NUTS data to bring it into normalised form."""
import click
import fiona
import fiona.transform
import shapely.geometry
import geopandas as gpd
import pandas as pd
import pycountry

from gadm import SCHEMA, _to_multi_polygon, _test_id_uniqueness
from conversion import eu_country_code_to_iso3
from utils import Config

OUTPUT_DRIVER = "GPKG"
LAYER_NAME = "nuts{layer_id}"


@click.group()
def nuts():
    pass


@nuts.command()
@click.argument("path_to_shapes")
@click.argument("path_to_attributes")
@click.argument("path_to_output")
def merge(path_to_shapes, path_to_attributes, path_to_output):
    """Merge NUTS shapes with attributes."""
    shapes = gpd.read_file(path_to_shapes)
    shapes.geometry = shapes.geometry.map(_to_multi_polygon)
    attributes = gpd.read_file(path_to_attributes)
    attributes = pd.DataFrame(attributes) # to be able to remove geo information
    del attributes["geometry"]
    shapes.merge(attributes, on="NUTS_ID").to_file(path_to_output, driver=OUTPUT_DRIVER)


@nuts.command()
@click.argument("path_to_nuts")
@click.argument("path_to_output")
@click.argument("config", type=Config())
def normalise(path_to_nuts, path_to_output, config):
    """Normalises raw NUTS data.

    Raw data contains all NUTS layers in one layer of one shapefile. The output
    of this function corresponds to the form the data is used in this analysis,
    where each geographical layer is stored in one layer of a GeoPackage.
    """
    with fiona.open(path_to_nuts, "r") as nuts_file:
        for layer_id in range(4):
            print("Building layer {}...".format(layer_id))
            _write_layer(nuts_file, config, path_to_output, layer_id)
    _test_id_uniqueness(path_to_output)


def _write_layer(nuts_file, config, path_to_output, layer_id):
    with fiona.open(path_to_output,
                    "w",
                    crs=config["crs"],
                    schema=SCHEMA,
                    driver=OUTPUT_DRIVER,
                    layer=LAYER_NAME.format(layer_id=layer_id)) as result_file:
        result_file.writerecords(_layer_features(nuts_file, config, layer_id))


def _layer_features(nuts_file, config, layer_id):
    for feature in filter(_in_layer_and_in_study_area(layer_id, config), nuts_file):
        new_feature = {}
        new_feature["properties"] = {}
        new_feature["properties"]["country_code"] = eu_country_code_to_iso3(feature["properties"]["CNTR_CODE"])
        new_feature["properties"]["id"] = feature["properties"]["NUTS_ID"]
        new_feature["properties"]["name"] = feature["properties"]["NAME_LATN"]
        new_feature["properties"]["region_type"] = "country" if layer_id == 0 else None
        new_feature["geometry"] = _all_parts_in_study_area_and_crs(feature, nuts_file.crs, config)
        yield new_feature


def _all_parts_in_study_area_and_crs(feature, src_crs, config):
    study_area = _study_area(config)
    region = _to_multi_polygon(feature["geometry"])
    if not study_area.contains(region):
        print("Removing parts of {} outside of study area.".format(feature["properties"]["NUTS_ID"]))
        new_region = shapely.geometry.MultiPolygon([polygon for polygon in region.geoms
                                                    if study_area.contains(polygon)])
        region = new_region
    geometry = shapely.geometry.mapping(region)
    return fiona.transform.transform_geom(
        src_crs=src_crs,
        dst_crs=config["crs"],
        geom=geometry
    )


def _in_layer_and_in_study_area(layer_id, config):
    def _in_layer_and_in_study_area(feature):
        return _in_layer(layer_id, feature) and _in_study_area(config, feature)
    return _in_layer_and_in_study_area


def _in_layer(layer_id, feature):
    if feature["properties"]["STAT_LEVL_"] == layer_id:
        return True
    else:
        return False


def _study_area(config):
    return shapely.geometry.box(
        minx=config["scope"]["bounds"]["x_min"],
        maxx=config["scope"]["bounds"]["x_max"],
        miny=config["scope"]["bounds"]["y_min"],
        maxy=config["scope"]["bounds"]["y_max"]
    )


def _in_study_area(config, feature):
    study_area = _study_area(config)
    countries = [pycountry.countries.lookup(country) for country in config["scope"]["countries"]]
    region = shapely.geometry.shape(feature["geometry"])
    country = pycountry.countries.lookup(eu_country_code_to_iso3(feature["properties"]["CNTR_CODE"]))
    if (country in countries) and (study_area.contains(region) or study_area.intersects(region)):
        return True
    else:
        print("Removing {} as it is outside of study area.".format(feature["properties"]["NUTS_ID"]))
        return False


if __name__ == "__main__":
    nuts()
