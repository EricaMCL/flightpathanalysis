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



##functions for terrain masking
##just use this function to create viewshed
