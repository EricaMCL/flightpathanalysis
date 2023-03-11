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
                                'OUTPUT': os.path.join(projectFolder, rawBuffer)})

    return projectFolder, rawBuffer

def findBufferRange(UseToErasePath, ToErasePath, uniqueIDFields, projectFolder, bufferDist):
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
        uniqueIDFields_Index = [useToEraseLyr_fields.index(uniqueIDFields[0]), useToEraseLyr_fields.index(uniqueIDFields[1])]
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

        out_features = projectFolder + "\\outfeature" + str(out_count) + '__' + str(bufferDist)
        processing.run("native:difference", {'INPUT': ToEraseLyr_selected,
                                             'OVERLAY': useToEraseLyr_selected,
                                             'OUTPUT': out_features, 'GRID_SIZE': None})

        bufferedFeatures.append(out_features + '.gpkg|layername=' + "outfeature" + str(out_count) + '__' + str(bufferDist))


    # merge all outputs
    outputPath = os.path.join(projectFolder, 'rawBuffer_' + str(bufferDist) + 'only')
    output = processing.run("native:mergevectorlayers", {'LAYERS': bufferedFeatures,
                                                'OUTPUT': outputPath})['OUTPUT']
    #outputLyr = output + '|layername=' + 'rawBuffer_' + str(bufferDist) + 'only'


    return output

##functions for terrain masking
##just use this function to create viewshed
