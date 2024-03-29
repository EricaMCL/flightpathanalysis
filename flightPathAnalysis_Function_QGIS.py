from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterString,
                       QgsProcessingParameterField,
                       QgsProcessingParameterDistance,
                       QgsProcessingFeedback,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterMultipleLayers,
                       QgsField,
                       QgsFeature,
                       QgsVectorLayer)
import glob
import os
import processing
import datetime


def replaceNonAlphaNum(myText, newXter):
    '''
    Purpose:  to check for non-alpha numeric xters
    replace them with user defined new character
    '''
    # go thru each xter. Check to see if it's alphanumeric.
    # If not, then replace it with the new character (newXter)
    for x in range(0, len(myText)):
        if not myText[x].isalnum():
            myText = myText.replace(myText[x], newXter)
    return myText


def convert_timedelta(duration):
    # convert timedelta to seconds (type: float)
    seconds = duration.total_seconds()
    seconds = seconds % 60
    return seconds


def rawBuffer(origFCLoc, origFCName, bufferDistanceInput, bufferDist, projectFolder, unit_no, unit_no_id,
              uwr_unique_Field):
    """
    (string, string, string, int, string) -> string, string
    origFCLoc: Folder of feature class to be buffered
    origFCName: name of feature class or shapefile to be buffered
    bufferDistanceInput: buffer value and unit. example: "1500 Meters"
    bufferNumber: buffer value. Use for naming output feature class. Assume units in meters. example: 1500
    unit_no_Field: field of unit number
    unit_no_id_Field: field of unit number id
    uwr_unique_Field: field for unique uwr id made from combining unit number and unit number id

    Purpose:
    Buffers given input feature class or dissolved feature class.
    Returns names of output GDB and buffer fc name.

    Output: buffered feature class

    """
    if origFCName.find(".shp") >= 0:
        origName = replaceNonAlphaNum(origFCName[:origFCName.find(".gpkg")],
                                      "_")  ###deleted +1 in  origFCName.find(".gpkg")+1
    else:
        origName = replaceNonAlphaNum(origFCName, "_")

    rawBuffer = "rawBuffer_" + origName + "_" + str(bufferDist)

    tempBufferLyr = processing.run("native:buffer",
                                   {'INPUT': os.path.join(origFCLoc, origFCName),
                                    'DISTANCE': bufferDist, 'SEGMENTS': 90, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0,
                                    'MITER_LIMIT': 2,
                                    'DISSOLVE': False, 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    tempBufferLyr_fid_removed = processing.run("native:deletecolumn",
                                               {'COLUMN': ['fid'],
                                                'INPUT': tempBufferLyr,
                                                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
    # ===========================================================================
    # Calculate the uwr_unique_id field value
    # ===========================================================================
    bufferLyr = processing.run("native:fieldcalculator",
                               {'FIELD_LENGTH': 100,
                                'FIELD_NAME': uwr_unique_Field,
                                'NEW_FIELD': True,
                                'FIELD_PRECISION': 0,
                                'FIELD_TYPE': 2,
                                'FORMULA': f' "{unit_no}" + \'__\' + "{unit_no_id}" ',
                                'INPUT': tempBufferLyr_fid_removed,
                                'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
    bufferLyrDist = processing.run("native:fieldcalculator",
                                   {'FIELD_LENGTH': 100,
                                    'FIELD_NAME': 'BUFF_DIST',
                                    'NEW_FIELD': True,
                                    'FIELD_PRECISION': 0,
                                    'FIELD_TYPE': 0,
                                    'FORMULA': f"'{bufferDist}'",
                                    'INPUT': bufferLyr,
                                    'OUTPUT': os.path.join(projectFolder, rawBuffer)})
    return projectFolder, rawBuffer


def findBufferRange(UseToErasePath, ToErasePath, uniqueIDFields, delFolder, bufferDist):
    useToEraseLyr = processing.run("native:savefeatures",
                                   {'INPUT': UseToErasePath,
                                    'OUTPUT': 'TEMPORARY_OUTPUT',
                                    'LAYER_NAME': '',
                                    'DATASOURCE_OPTIONS': '',
                                    'LAYER_OPTIONS': ''})['OUTPUT']
    useToEraseLyr_saved = QgsVectorLayer((useToEraseLyr), "", "ogr")

    ToEraseLyr = processing.run("native:savefeatures",
                                {'INPUT': ToErasePath,
                                 'OUTPUT': 'TEMPORARY_OUTPUT',
                                 'LAYER_NAME': '', 'DATASOURCE_OPTIONS': '',
                                 'LAYER_OPTIONS': ''})['OUTPUT']
    ToEraseLyr_saved = QgsVectorLayer((ToEraseLyr), "", "ogr")

    # count of features
    out_count = 0

    # list of erased fc to merge together
    bufferedFeatures = []
    bufferedFeatures_delPath = []

    # select unique id in each fc and erase area of second fc from first fc. Creates a fc output
    for feature in useToEraseLyr_saved.getFeatures():
        useToEraseLyr_fields = useToEraseLyr_saved.fields().names()
        uniqueIDFields_Index = [useToEraseLyr_fields.index(uniqueIDFields[0]),
                                useToEraseLyr_fields.index(uniqueIDFields[1])]
        unit_no_attribute = feature.attributes()[uniqueIDFields_Index[0]]
        if type(unit_no_attribute) == int:
            expression = '(\"' + uniqueIDFields[0] + '\" = ' + str(feature.attributes()[uniqueIDFields_Index[0]]) + ')'
        else:
            expression = '(\"' + uniqueIDFields[0] + '\" = \'' + str(
                feature.attributes()[uniqueIDFields_Index[0]]) + "')"
        countField = len(uniqueIDFields)
        if countField > 1:
            for i in range(1, countField):
                if type(feature.attributes()[uniqueIDFields_Index[i]]) == int:
                    expression += 'AND (\"' + uniqueIDFields[i] + '\" = ' + str(
                        feature.attributes()[uniqueIDFields_Index[i]]) + ')'
                else:
                    expression += 'AND (\"' + uniqueIDFields[i] + '\" = \'' + str(
                        feature.attributes()[uniqueIDFields_Index[i]]) + "')"

        out_count += 1

        useToEraseLyr_selected = processing.run("native:extractbyexpression",
                                                {'EXPRESSION': expression,
                                                 'INPUT': useToEraseLyr,
                                                 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        ToEraseLyr_selected = processing.run("native:extractbyexpression",
                                             {'EXPRESSION': expression,
                                              'INPUT': ToEraseLyr,
                                              'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']
        outFCFolder = os.path.join(delFolder, 'out_features')
        if not os.path.exists(outFCFolder):
            try:
                os.mkdir(outFCFolder)
            except:
                continue
        out_features = os.path.join(outFCFolder , 'outFeature' + str(out_count) + '__' + str(bufferDist))
        processing.run("native:difference", {'INPUT': ToEraseLyr_selected,
                                             'OVERLAY': useToEraseLyr_selected,
                                             'OUTPUT': out_features, 'GRID_SIZE': None})

        bufferedFeatures.append(out_features + '.gpkg')
        #bufferedFeatures_delPath.append(out_features + '.gpkg')

    projectFolder = os.path.split(delFolder)[0]
    # merge all outputs
    outputPath = os.path.join(projectFolder, 'rawBuffer_' + str(bufferDist) + 'only')
    output = processing.run("native:mergevectorlayers", {'LAYERS': bufferedFeatures,
                                                         'OUTPUT': outputPath})['OUTPUT']

    for fname in os.listdir(outFCFolder):
        if fname.startswith('outFeature'):
            try:
                os.remove(os.path.join(outFCFolder, fname))
            except:
                continue


    # outputLyr = output + '|layername=' + 'rawBuffer_' + str(bufferDist) + 'only'

    return output


def makeViewshed(uwrList, uwrBuffered, buffDistance, unit_no, unit_no_id, uwr_unique_Field, tempFolder, DEM, viewshed,
                 minElevViewshed):
    UWR_noBuffer = 'UWR_noBuffer'
    UWR_Buffer = 'UWR_Buffer'

    # ==============================================================
    # name of feature layers
    # ==============================================================
    # UWR_noBuffer_lyr = 'UWR_noBuffer_lyr'
    # UWRVertices_lyr = 'UWRVertices_lyr'
    # UWR_Buffer_lyr = 'UWR_Buffer_lyr'
    # UWR_DEMPoints_lyr = 'UWR_DEMPoints_lyr'
    # polygonViewshed_lyr = 'polygonViewshed_lyr'
    # polygon_aglViewshed_lyr = 'polygon_aglViewshed_lyr'

    # ==============================================================
    # create a lyr with relevent UWR - 0m buffer
    # ==============================================================
    uwrSet_str = "','".join(uwrList)
    expression = uwr_unique_Field + r" in ('" + uwrSet_str + r"') and BUFF_DIST = 0"
    UWR_noBuffer_lyr = processing.run("native:extractbyexpression",
                                      {'EXPRESSION': expression,
                                       'INPUT': uwrBuffered,
                                       'OUTPUT': os.path.join(tempFolder, UWR_noBuffer)})['OUTPUT']

    # ==============================================================
    # Generalize/simplify UWR (0m buffer)
    # ==============================================================
    simplifyUWR = processing.run("native:simplifygeometries",
                                 {'INPUT': UWR_noBuffer_lyr,
                                  'METHOD': 0,
                                  'TOLERANCE': 1,
                                  'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    # ==============================================================
    # Convert uwr polygons to vertices
    # ==============================================================
    UWRVertices = processing.run("sagang:convertpolygonlineverticestopoints",
                                 {'SHAPES': simplifyUWR,
                                  'POINTS': 'TEMPORARY_OUTPUT'})['POINTS']

    # ==============================================================
    # Get DEM of vertices
    # ==============================================================
    DEM_grid = processing.run("sagang:copygrid", {'GRID': DEM, 'COPY': os.path.join(tempFolder, 'DEMElev.sdat')})[
        'COPY']

    UWRVertices_Lyr_temp = processing.run("sagang:addrastervaluestopoints",
                                          {'SHAPES': UWRVertices,
                                           'GRIDS': [DEM_grid],
                                           'RESULT': os.path.join(tempFolder, 'verticeLyr_temp'),
                                           'RESAMPLING': 3})['RESULT']

    UWRVertices_Lyr = processing.run("native:joinattributesbylocation",
                                     {'INPUT': UWRVertices_Lyr_temp + '.shp',
                                      'JOIN': simplifyUWR,
                                      'PREDICATE': [0],
                                      'JOIN_FIELDS': [unit_no, unit_no_id, uwr_unique_Field, 'BUFF_DIST'],
                                      'METHOD': 0, 'DISCARD_NONMATCHING': False, 'PREFIX': '',
                                      'OUTPUT': os.path.join(tempFolder, 'verticeLyr_temp')})['OUTPUT']

    # ==============================================================
    # Make feature class with relevant UWR buffered. includes all buffer distances
    # ==============================================================
    expression = uwr_unique_Field + " in ('" + uwrSet_str + "')"
    UWR_Buffer = processing.run("native:extractbyexpression",
                                {'EXPRESSION': expression,
                                 'INPUT': uwrBuffered,
                                 'OUTPUT': os.path.join(tempFolder, UWR_Buffer)})['OUTPUT']

    # ==============================================================
    #
    # ==============================================================
    viewshedList = []
    viewshed_delPath = []
    minElevViewshedList = []
    minElevViewshed_delPath = []

    for uwr in uwrList:
        uwrstarttime = datetime.datetime.now()
        name_uwr = replaceNonAlphaNum(uwr, "_")
        rasterViewshed = "rasterViewshed_" + name_uwr
        agl_rasterViewshed = "agl_rasterViewshed" + name_uwr
        polygonViewshed = "polygonViewshed_" + name_uwr
        totalViewshed = "totalViewshed_" + name_uwr
        totalViewshed_dis = "dis" + totalViewshed
        int_aglViewshed = "int_aglViewshed" + name_uwr
        polygon_aglViewshed = "polygon_aglViewshed" + name_uwr
        dissolved_aglViewshed = "dissolved_aglViewshed" + name_uwr

        UWR_DEMClip = "DEMClip" + name_uwr
        BufferUWR_DEMClip = "Buffer_DEMClip_" + name_uwr
        UWR_DEMPoints = "UWR_DEMPoints" + name_uwr
        UWRBuffer_DEMPoints = "UWRBuffer_DEMPoints" + name_uwr
        UWR_ViewshedObsPoints = "UWR_ViewshedObsPoints" + name_uwr

        uwr_no = uwr[:uwr.find("__")]
        uwr_no_id = uwr[uwr.find("__") + 2:]

        # ==============================================================
        # Check to find the right query depending on if uwr fields are integer or text
        # ==============================================================
        UWR_Buffer_lyr = QgsVectorLayer((UWR_Buffer), "", "ogr")
        expression = None
        for feature in UWR_Buffer_lyr.getFeatures():
            UWR_Buffer_lyr_fields = UWR_Buffer_lyr.fields().names()
            unit_no_index = [UWR_Buffer_lyr_fields.index(unit_no), UWR_Buffer_lyr_fields.index(unit_no)]
            unit_no_attribute = feature.attributes()[unit_no_index[0]]
            unit_no_id_index = [UWR_Buffer_lyr_fields.index(unit_no_id), UWR_Buffer_lyr_fields.index(unit_no_id)]
            unit_no_id_attribute = feature.attributes()[unit_no_id_index[0]]

            if type(unit_no_attribute) == int:
                expression = '(\"' + unit_no + '\" = ' + uwr_no + ')'
            else:
                expression = '(\"' + unit_no + '\" = \'' + uwr_no + "')"

            if type(unit_no_id_attribute) == int:
                expression += ' AND (\"' + unit_no_id + '\" = ' + uwr_no_id + ')'
            else:
                expression += ' AND (\"' + unit_no_id + '\" = \'' + uwr_no_id + "')"

            break

        # ==============================================================
        # Clip DEM using max buffer range
        # ==============================================================

        UWR_Buffer_selected = processing.run("native:extractbyexpression",
                                             {'EXPRESSION': expression,
                                              'INPUT': UWR_Buffer,
                                              'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        UWR_Buffer_selected_ext = processing.run("native:polygonfromlayerextent",
                                                 {'INPUT': UWR_Buffer_selected,
                                                  'ROUND_TO': 0, 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        demClipped = processing.run("gdal:cliprasterbymasklayer",
                                    {'INPUT': DEM,
                                     'MASK': UWR_Buffer_selected_ext,
                                     'SOURCE_CRS': None, 'TARGET_CRS': None, 'TARGET_EXTENT': None, 'NODATA': None,
                                     'ALPHA_BAND': False, 'CROP_TO_CUTLINE': True,
                                     'KEEP_RESOLUTION': True, 'SET_RESOLUTION': False, 'X_RESOLUTION': None,
                                     'Y_RESOLUTION': None, 'MULTITHREADING': False,
                                     'OPTIONS': '', 'DATA_TYPE': 0, 'EXTRA': '',
                                     'OUTPUT': os.path.join(tempFolder, f'{BufferUWR_DEMClip}.tif')})['OUTPUT']

        # ==============================================================
        # Clip DEM using original uwr range
        # ==============================================================
        UWR_Buffer_selected_orig = processing.run("native:extractbyexpression",
                                                  {'EXPRESSION': expression + " and (BUFF_DIST = 0)",
                                                   'INPUT': UWR_Buffer,
                                                   'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        UWR_Buffer_selected_ext_orig = processing.run("native:polygonfromlayerextent",
                                                      {'INPUT': UWR_Buffer_selected_orig,
                                                       'ROUND_TO': 0, 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        demClipped_orig = processing.run("gdal:cliprasterbymasklayer",
                                         {'INPUT': DEM,
                                          'MASK': UWR_Buffer_selected_ext_orig,
                                          'SOURCE_CRS': None, 'TARGET_CRS': None, 'TARGET_EXTENT': None, 'NODATA': None,
                                          'ALPHA_BAND': False, 'CROP_TO_CUTLINE': True,
                                          'KEEP_RESOLUTION': True, 'SET_RESOLUTION': False, 'X_RESOLUTION': None,
                                          'Y_RESOLUTION': None, 'MULTITHREADING': False,
                                          'OPTIONS': '', 'DATA_TYPE': 0, 'EXTRA': '',
                                          'OUTPUT': os.path.join(tempFolder, f'{UWR_DEMClip}.tif')})['OUTPUT']

        # ==============================================================
        # Convert original clipped DEM to points
        # ==============================================================
        rasToPoi = processing.run("native:pixelstopoints", {'INPUT_RASTER': demClipped_orig,
                                                            'RASTER_BAND': 1,
                                                            'FIELD_NAME': 'DEMElev',
                                                            'OUTPUT': os.path.join(tempFolder, UWR_DEMPoints)})

        vertice_Selected = processing.run("native:extractbyexpression",
                                          {'EXPRESSION': expression,
                                           'INPUT': UWRVertices_Lyr,
                                           'OUTPUT': os.path.join(tempFolder, f'uwrSelected_{name_uwr}')})['OUTPUT']

        # ==============================================================
        # Get list of DEM values in UWR that are higher than the min DEM value of vertices
        # ==============================================================
        vertice_Selected_lyr = QgsVectorLayer((vertice_Selected), "", "ogr")
        minValue = 9999
        for feature in vertice_Selected_lyr.getFeatures():
            DEMValue_Index = (vertice_Selected_lyr.fields().names()).index('DEMElev')
            DEMvalue = feature.attributes()[DEMValue_Index]
            if DEMvalue > 0 and DEMvalue < minValue:
                minValue = DEMvalue

        UWRDEMpoi_Selected = processing.run("native:extractbyexpression",
                                            {'EXPRESSION': "DEMElev > " + str(minValue),
                                             'INPUT': UWRVertices_Lyr,
                                             'OUTPUT': os.path.join(tempFolder,
                                                                    UWR_DEMPoints + '_selected' + str(minValue))})[
            'OUTPUT']

        # ==============================================================
        # Add all higher than min DEM value points to vertices layer
        # ==============================================================
        UWRVertices_merge = processing.run("native:mergevectorlayers",
                                           {'LAYERS': [UWRDEMpoi_Selected, vertice_Selected],
                                            'CRS': None,
                                            'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        # ==============================================================
        # Make raster viewshed
        # ==============================================================
        viewPoints = processing.run("visibility:createviewpoints", {
            'OBSERVER_POINTS': UWRVertices_merge,
            'DEM': demClipped, 'OBSERVER_ID': '',
            'RADIUS': 5000, 'RADIUS_FIELD': '', 'OBS_HEIGHT': 1, 'OBS_HEIGHT_FIELD': 'DEMElev', 'TARGET_HEIGHT': 0,
            'TARGET_HEIGHT_FIELD': '', 'RADIUS_IN_FIELD': '', 'AZIM_1_FIELD': '', 'AZIM_2_FIELD': '',
            'ANGLE_UP_FIELD': '', 'ANGLE_DOWN_FIELD': '', 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        rasViewshed = processing.run("visibility:viewshed",
                                     {'ANALYSIS_TYPE': 0,
                                      'OBSERVER_POINTS': viewPoints,
                                      'DEM': demClipped,
                                      'USE_CURVATURE': False, 'REFRACTION': 0.13, 'OPERATOR': 0,
                                      'OUTPUT': os.path.join(tempFolder, rasterViewshed + '.tif')})['OUTPUT']

        agl_rasViewshed = processing.run("visibility:viewshed",
                                         {'ANALYSIS_TYPE': 1,
                                          'OBSERVER_POINTS': viewPoints,
                                          'DEM': demClipped,
                                          'USE_CURVATURE': False, 'REFRACTION': 0.13, 'OPERATOR': 1,
                                          'OUTPUT': os.path.join(tempFolder, agl_rasterViewshed + '.tif')})['OUTPUT']

        viewshedRasToPoly = processing.run("native:pixelstopolygons",
                                           {'INPUT_RASTER': rasViewshed,
                                            'RASTER_BAND': 1, 'FIELD_NAME': 'VALUE',
                                            'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        # ==============================================================
        # Select all direct viewshed area (visible area)
        # ==============================================================
        selectRasToPoly = processing.run("native:extractbyexpression", {
            'INPUT': viewshedRasToPoly,
            'EXPRESSION': 'VALUE <> 0', 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        polyMergeUWR = processing.run("native:mergevectorlayers",
                                      {'LAYERS': [UWR_Buffer_selected_orig, selectRasToPoly],
                                       'CRS': None,
                                       'OUTPUT': os.path.join(tempFolder, totalViewshed)})['OUTPUT']

        polyMergeUWR_dis = processing.run("native:dissolve", {'INPUT': polyMergeUWR,
                                                              'FIELD': [], 'SEPARATE_DISJOINT': False,
                                                              'OUTPUT': os.path.join(tempFolder, totalViewshed_dis)})[
            'OUTPUT']

        viewshedList.append(polyMergeUWR_dis)
        viewshed_delPath.append(f'{polyMergeUWR_dis}' + '.gpkg')

        agl_rasViewshedRasToPoly = processing.run("native:pixelstopolygons",
                                                  {'INPUT_RASTER': agl_rasViewshed,
                                                   'RASTER_BAND': 1, 'FIELD_NAME': 'VALUE',
                                                   'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        agl_rasViewshed_dis = processing.run("native:dissolve", {'INPUT': agl_rasViewshedRasToPoly,
                                                                 'FIELD': ['VALUE'], 'SEPARATE_DISJOINT': False,
                                                                 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        agl_rasViewshed_join = processing.run("native:joinattributesbylocation", {
            'INPUT': agl_rasViewshed_dis,
            'PREDICATE': [0],
            'JOIN': UWR_Buffer_selected,
            'JOIN_FIELDS': [], 'METHOD': 0, 'DISCARD_NONMATCHING': False, 'PREFIX': '', 'OUTPUT': 'TEMPORARY_OUTPUT'})[
            'OUTPUT']

        agl_rasViewshed_drop = processing.run("native:deletecolumn", {
            'INPUT': agl_rasViewshed_join,
            'COLUMN': ['fid'], 'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

        agl_rasViewshed_clip = processing.run("native:clip",
                                              {'INPUT': agl_rasViewshed_drop,
                                               'OVERLAY': UWR_Buffer_selected,
                                               'OUTPUT': os.path.join(tempFolder, dissolved_aglViewshed)})['OUTPUT']

        minElevViewshedList.append(agl_rasViewshed_clip)
        minElevViewshed_delPath.append(agl_rasViewshed_clip + '.gpkg')

    projectFolder = os.path.split(tempFolder)[0]
    viewshed_final = processing.run("native:mergevectorlayers",
                                    {'LAYERS': viewshedList,
                                    'OUTPUT': os.path.join(projectFolder, 'viewshed')})['OUTPUT']
    minElevViewshed_temp = processing.run("native:mergevectorlayers",
                                           {'LAYERS': minElevViewshedList,
                                            'OUTPUT': 'TEMPORARY_OUTPUT'})['OUTPUT']

    minElevViewshed_final  = processing.run("native:fieldcalculator", {
        'INPUT': minElevViewshed_temp ,
        'FIELD_NAME': 'gridcode', 'FIELD_TYPE': 1, 'FIELD_LENGTH': 100, 'FIELD_PRECISION': 0, 'FORMULA': '"VALUE"',
        'OUTPUT': os.path.join(projectFolder,'minElevViewshed')})['OUTPUT']
    for feature in viewshed_delPath or minElevViewshed_delPath:
        try:
            os.remove(feature)
        except:
            continue

    return [viewshed_final, minElevViewshed_final]

##functions for terrain masking
##just use this function to create viewshed
