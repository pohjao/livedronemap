import os
import numpy as np
import cv2
import time
from osgeo import ogr
from ExifData import getExif, restoreOrientation
from EoData import convertCoordinateSystem, Rot3D
from Boundary import boundary
from BackprojectionResample import projectedCoord, backProjection, resample, createGeoTiff


def export_bbox_to_wkt(bbox):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    ring.AddPoint(bbox[0][0], bbox[2][0])
    ring.AddPoint(bbox[0][0], bbox[3][0])
    ring.AddPoint(bbox[1][0], bbox[2][0])
    ring.AddPoint(bbox[1][0], bbox[3][0])
    geom_poly = ogr.Geometry(ogr.wkbPolygon)
    geom_poly.AddGeometry(ring)
    wkt = geom_poly.ExportToWkt()
    return wkt


def rectify(project_path, img_fname, img_rectified_fname, eo, ground_height, sensor_width):
    """
    In order to generate individual ortho-image, this function rectifies a given drone image on a reference plane.
    :param img_fname:
    :param eo_fname:
    :param project_path:
    :param ground_height: Ground height in m
    :param sensor_width: Width of the sensor in mm
    :return File name of rectified image, boundary polygon in WKT  string
    """
    # TODO: 현재 EPSG:5186에서 작업하게 되어있는데, EPGS:4326에서 작업하도록 수정
    img_path = os.path.join(project_path, img_fname)

    start_time = time.time()

    print('Read the image - ' + img_fname)
    image = cv2.imread(img_path)

    # 0. Extract EXIF data from a image
    focal_length, orientation = getExif(img_path) # unit: m

    # 1. Restore the image based on orientation information
    restored_image = restoreOrientation(image, orientation)

    image_rows = restored_image.shape[0]
    image_cols = restored_image.shape[1]

    pixel_size = sensor_width / image_cols  # unit: mm/px
    pixel_size = pixel_size / 1000  # unit: m/px

    end_time = time.time()
    print("--- %s seconds ---" % (time.time() - start_time))

    read_time = end_time - start_time

    print('Read EOP - ' + img_fname)
    print('Latitude | Longitude | Height | Omega | Phi | Kappa')
    eo = convertCoordinateSystem(eo)
    R = Rot3D(eo)

    # 2. Extract a projected boundary of the image
    bbox = boundary(restored_image, eo, R, ground_height, pixel_size, focal_length)
    print("--- %s seconds ---" % (time.time() - start_time))

    gsd = (pixel_size * (eo[2] - ground_height)) / focal_length  # unit: m/px

    # Boundary size
    boundary_cols = int((bbox[1, 0] - bbox[0, 0]) / gsd)
    boundary_rows = int((bbox[3, 0] - bbox[2, 0]) / gsd)

    print('projectedCoord')
    start_time = time.time()
    proj_coords = projectedCoord(bbox, boundary_rows, boundary_cols, gsd, eo, ground_height)
    print("--- %s seconds ---" % (time.time() - start_time))

    # Image size
    image_size = np.reshape(restored_image.shape[0:2], (2, 1))

    print('backProjection')
    start_time = time.time()
    backProj_coords = backProjection(proj_coords, R, focal_length, pixel_size, image_size)
    print("--- %s seconds ---" % (time.time() - start_time))

    print('resample')
    start_time = time.time()
    b, g, r, a = resample(backProj_coords, boundary_rows, boundary_cols, image)
    print("--- %s seconds ---" % (time.time() - start_time))

    print('Save the image in GeoTiff')
    start_time = time.time()
    dst = os.path.join(project_path, img_rectified_fname)
    createGeoTiff(b, g, r, a, bbox, gsd, boundary_rows, boundary_cols, dst)
    print("--- %s seconds ---" % (time.time() - start_time))

    print('*** Processing time per each image')
    print("--- %s seconds ---" % (time.time() - start_time + read_time))

    bbox_wkt = export_bbox_to_wkt(bbox)
    return img_rectified_fname, bbox_wkt
