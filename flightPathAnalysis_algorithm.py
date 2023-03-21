# -*- coding: utf-8 -*-

"""
/***************************************************************************
 flightPathAnalysis
                                 A QGIS plugin
 Analysis the flight path impact on UWR
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-02-28
        copyright            : (C) 2023 by Erica Liu
        email                : halamay1029@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Erica Liu'
__date__ = '2023-02-28'
__copyright__ = '(C) 2023 by Erica Liu'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

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
from .flightPathAnalysis_Function_QGIS import rawBuffer, findBufferRange, replaceNonAlphaNum, convert_timedelta
import shutil
from pathlib import Path



class createUWRBuffer(QgsProcessingAlgorithm):
    """
    This is an example algorithm that takes a vector layer and
    creates a new identical one.

    It is meant to be used as an example of how to create your own
    algorithms and explain methods and variables used to do it. An
    algorithm like this will be available in all elements, and there
    is not need for additional work.

    All Processing algorithms should extend the QgsProcessingAlgorithm
    class.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.

    origUWR = 'origUWR'
    projectFolder = 'projectFolder'
    unit_id = 'unit_id'
    unit_id_no = 'unit_id_no'
    buffDistIS_high = 'buffDistIS_high'
    buffDistIS_moderate = 'buffDistIS_moderate'
    buffDistIS_low = 'buffDistIS_low'

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        # ===========================================================================
        # OrigUWR - Input vector polygon
        # ===========================================================================
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.origUWR, self.tr('Input original UWR'), [QgsProcessing.TypeVectorPolygon]))
        # ===========================================================================
        # Project Folder
        # ===========================================================================
        self.addParameter(QgsProcessingParameterFile(
            self.projectFolder, self.tr('Project Folder'), QgsProcessingParameterFile.Folder))
        # ===========================================================================
        # unit_id / unit_id_no - Input string
        # User selects from the field list derived from OrigUWR
        # ===========================================================================
        self.addParameter(QgsProcessingParameterField(
            self.unit_id, self.tr('Input unit id field, column has text like u-2-002'), 'unit_id', self.origUWR))

        self.addParameter(QgsProcessingParameterField(
            self.unit_id_no, self.tr('Input unit id field, column has text like Mg-059'), 'unit_id', self.origUWR))
        # ===========================================================================
        # bufferDistIS_high/moderate/low - Input string, with default value 500/1000/1500
        # three buffer range represents different incursion severity range
        # ===========================================================================
        self.addParameter(QgsProcessingParameterString(
            self.buffDistIS_high, self.tr('Buffer distance - High Incursion Severity'), 500))

        self.addParameter(QgsProcessingParameterString(
            self.buffDistIS_moderate, self.tr('Buffer distance - Moderate Incursion Severity'), 1000))

        self.addParameter(QgsProcessingParameterString(
            self.buffDistIS_low, self.tr('Buffer distance - Low Incursion Severity'), 1500))


    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """
        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        origUWR_source = self.parameterAsSource(parameters, self.origUWR, context)
        origUWR = parameters['origUWR']
        projectFolder = parameters['projectFolder']
        feedback.setProgressText(str(origUWR))
        uwrBufferedPath = os.path.join(projectFolder, 'uwrBuffered')
        delFolder = os.path.join(projectFolder, 'delFolder')
        final = None

        try:

            if os.path.exists(delFolder):
                shutil.rmtree(delFolder)
                os.mkdir(delFolder)
            else:
                os.mkdir(delFolder)

            # ==============================================================
            # unit_no, eg. u-2-002
            # unit_no_id, eg. Mg-106
            # unit_unique_field, field that combines uwr number and uwr unit number
            # ==============================================================
            unit_no = parameters['unit_id']
            unit_no_id = parameters['unit_id_no']
            uwr_unique_Field = "uwr_unique_id"

            bufferDistList = [int(parameters['buffDistIS_high']), int(parameters['buffDistIS_moderate']),
                              int(parameters['buffDistIS_low'])]
            feedback.setProgressText(str(bufferDistList))

            # ===========================================================================
            # Check if the input vector includes invalid geometry
            # ===========================================================================
            result = processing.run("qgis:checkvalidity", {
                'INPUT_LAYER': parameters['origUWR']})
            errorCount = result['ERROR_COUNT']
            feedback.setProgressText(str(errorCount))

            # ===========================================================================
            # Fix the input geometry if invalid found, and replace the input for further process
            # ===========================================================================
            if errorCount > 0:
                fixGeom = processing.run("native:fixgeometries",
                                         {'INPUT': parameters['origUWR'],
                                          'OUTPUT': 'TEMPORARY_OUTPUT'})
                feedback.setProgressText('Geometry fixed')
                origUWR = fixGeom['OUTPUT']

            # ==============================================================
            # Get list of relevant UWR
            # ==============================================================
            origUWRFieldList = origUWR.fields().names()
            unit_no_index = origUWRFieldList.index(unit_no)
            unit_no_id_index = origUWRFieldList.index(unit_no_id)
            feedback.setProgressText(f'{unit_no_id_index, unit_no_index}')
            uwrSet = set()
            for feature in origUWR.getFeatures():
                uwr_unique_Field_value = f'{feature.attributes()[unit_no_index]}__{feature.attributes()[unit_no_id_index]}'
                uwrSet.add(uwr_unique_Field_value)
            feedback.setProgressText(f'{uwr_unique_Field} added and updated')

            # ==============================================================
            # Check existence of uwrBuffered in project folder
            # ==============================================================
            uwrBuffered_exist = os.path.isfile(uwrBufferedPath + '.gpkg')

            # ==============================================================
            # Get list of uwr that have buffers created
            # ==============================================================
            if uwrBuffered_exist:

                feedback.setProgressText(f'uwrBuffered exists in project folder.')
                createdUWRSet = set()
                uwrBuffered_layer = QgsVectorLayer((uwrBufferedPath + '.gpkg'), "uwrBuffered", "ogr")
                uwrBufferedFieldList = uwrBuffered_layer.fields().names()
                feedback.setProgressText(f'{uwrBufferedFieldList}')
                uwr_unique_Field_index = uwrBufferedFieldList.index(uwr_unique_Field)
                feedback.setProgressText(f'{uwrBufferedFieldList}')
                for feature in uwrBuffered_layer.getFeatures():
                    uwr_unique_Field_value =  f'{feature.attributes()[uwr_unique_Field_index]}'
                    createdUWRSet.add(uwr_unique_Field_value)

                uwrRequireSet = uwrSet - createdUWRSet
                feedback.setProgressText(f'{uwrSet} --uwrSet')
                feedback.setProgressText(f'{createdUWRSet} -- createdUWRSet')
                feedback.setProgressText(f'{uwrRequireSet} --uwrRequireSet')

            else:
                uwrRequireSet = uwrSet
                feedback.setProgressText(f'uwrBuffered NOT exists in project folder.')


            if len(uwrRequireSet) > 0:
                if uwrBuffered_exist:
                # ==============================================================
                # Make new field in copy of orig UWR FC for unique UWR id.
                # DIFFERENT FROM unique uwr id. make it so that there's no way this field existed before
                # ==============================================================
                    tempUniqueUWRField = 'tempUniqueUWRField'
                    if tempUniqueUWRField not in origUWRFieldList:
                        tempGPKG = processing.run("native:fieldcalculator",
                                                  {'FIELD_LENGTH': 100,
                                                   'FIELD_NAME': tempUniqueUWRField,
                                                   'NEW_FIELD': True,
                                                   'FIELD_PRECISION': 0,
                                                   'FIELD_TYPE': 2,
                                                   'FORMULA': f' "{unit_no}" + \'__\' + "{unit_no_id}" ',
                                                   'INPUT': origUWR,
                                                   'OUTPUT': 'TEMPORARY_OUTPUT'}, context=context, feedback=feedback)['OUTPUT']


                    # ==============================================================
                    # Select require uwr by making query with uwrRequireSet
                    # ==============================================================
                    uwrList_String = "','".join(uwrRequireSet)
                    unbufferedFL = os.path.join(projectFolder, 'unbufferedUWR')
                    expression = tempUniqueUWRField + " in ('" + uwrList_String + "')"
                    unbufferedFLPath = processing.run("native:extractbyexpression",
                                   {'EXPRESSION': expression,
                                    'INPUT': tempGPKG,
                                    'OUTPUT': unbufferedFL})['OUTPUT']
                    feedback.setProgressText(f'unBufferedUWR created in {unbufferedFL}')
                    requireUWRLayer = unbufferedFLPath
                else:
                    requireUWRLayer = origUWR
                    feedback.setProgressText('requireUWRLayer = origUWR')

                # ==============================================================
                # Dissolves input feature class by dissolveFields list if list is given
                # This is to avoid errors for multi-part uwr that have been split into
                # separate features in the original uwr feature class.
                # ==============================================================
                dissolvedOrigPath = os.path.join(projectFolder, 'dissolve')
                dissolvedOrig = processing.run("native:dissolve",
                                               {'FIELD': ['UWR_TAG', 'UNIT_NO'],
                                                'INPUT': requireUWRLayer,
                                                'OUTPUT': 'TEMPORARY_OUTPUT',
                                                'SEPARATE_DISJOINT': False})['OUTPUT']
                dissolvedOrig_fid_removed = processing.run("native:deletecolumn",
                                               {'COLUMN': ['fid'],
                                                'INPUT': dissolvedOrig,
                                                'OUTPUT': dissolvedOrigPath})['OUTPUT']

                # ============re==================================================
                # Start list of intermediate features to be deleted
                # ==============================================================
                uwrOnly = "BufferUWROnly"
                delFC = [os.path.join(projectFolder, uwrOnly)]

                # ==============================================================
                # Create raw buffers
                # ==============================================================
                rawBufferDict = {}
                for bufferDist in bufferDistList:
                    rawBufferLoc, rawBufferName = rawBuffer(projectFolder, 'dissolve.gpkg',
                                                  str(bufferDist) + 'Meters', bufferDist, delFolder,
                                                      unit_no, unit_no_id, uwr_unique_Field)
                    rawBufferDict[bufferDist] = [rawBufferLoc, rawBufferName]
                    delFC.append(os.path.join(rawBufferLoc, rawBufferName))
                    feedback.setProgressText(f"raw buffer created, {rawBufferName}")

                # ==============================================================
                # Get donut shaped buffer to only get list of buffered donut polygons
                # that will be merge together to the final layer
                # ==============================================================
                requireMergeBufferList = []

                # ==============================================================
                # Go through each buffer distance to get the donut shapes of
                # only the area for each buffer distance
                # ==============================================================
                uniqueIDFields = [unit_no, unit_no_id]
                sortBufferDistList = list(sorted(bufferDistList))
                feedback.setProgressText(f'{sortBufferDistList} -- sortedBuffer')
                for bufferDist in sortBufferDistList:
                    ToEraseLoc = rawBufferDict[bufferDist][0]
                    ToEraseName = rawBufferDict[bufferDist][1] + '.gpkg'
                    ToErasePath = os.path.join(ToEraseLoc, ToEraseName)
                    feedback.setProgressText(f'{ToEraseLoc} and {ToEraseName}')
                    feedback.setProgressText(f'{bufferDist} -- Bufferdist')

                    if sortBufferDistList.index(bufferDist) == 0:
                        onlyBufferDist = findBufferRange(dissolvedOrig_fid_removed, ToErasePath, uniqueIDFields, delFolder, bufferDist)
                        feedback.setProgressText(f'UseToErasePath - {dissolvedOrig_fid_removed}')
                        feedback.setProgressText(f'ToErasePath - {ToErasePath}')
                    else:
                        prevIndex = sortBufferDistList.index(bufferDist) - 1
                        prevBufferDist = sortBufferDistList[prevIndex]
                        prevBufferPath = os.path.join(rawBufferDict[prevBufferDist][0], rawBufferDict[prevBufferDist][1] + '.gpkg')
                        feedback.setProgressText(prevBufferPath)
                        feedback.setProgressText(f'UseToErasePath - {prevBufferPath}')
                        feedback.setProgressText(f'ToErasePath - {ToErasePath}')
                        onlyBufferDist = findBufferRange(prevBufferPath, ToErasePath, uniqueIDFields, delFolder, bufferDist)

                    requireMergeBufferList.append(onlyBufferDist)
                    feedback.setProgressText(f'appended uwronly{onlyBufferDist} -- onlyBufferDist')

                # ==============================================================
                # Create bufferUWROnly_NEW with uwr_unique_field and BUFF_DIST fields
                # ==============================================================
                uwrOnlyNewPath = os.path.join(projectFolder, uwrOnly)
                uwrOnly_new = processing.run("native:savefeatures",
                                               {'INPUT': dissolvedOrig_fid_removed,
                                                'OUTPUT': 'TEMPORARY_OUTPUT',
                                                'LAYER_NAME': '',
                                                'DATASOURCE_OPTIONS': '',
                                                'LAYER_OPTIONS': ''})['OUTPUT']

                uwrOnly_new_uniField = processing.run("native:fieldcalculator",
                                       {'FIELD_LENGTH': 100,
                                        'FIELD_NAME': uwr_unique_Field,
                                        'NEW_FIELD': True,
                                        'FIELD_PRECISION': 0,
                                        'FIELD_TYPE': 2,
                                        'FORMULA': f' "{unit_no}" + \'__\' + "{unit_no_id}" ',
                                        'INPUT': uwrOnly_new,
                                        'OUTPUT': 'TEMPORARY_OUTPUT'}, context=context, feedback=feedback)['OUTPUT']

                uwrOnly_new_uniField_buffDist = processing.run("native:fieldcalculator",
                                       {'FIELD_LENGTH': 100,
                                        'FIELD_NAME': 'BUFF_DIST',
                                        'NEW_FIELD': True,
                                        'FIELD_PRECISION': 0,
                                        'FIELD_TYPE': 0,
                                        'FORMULA': 0,
                                        'INPUT': uwrOnly_new_uniField,
                                        'OUTPUT': uwrOnlyNewPath}, context=context, feedback=feedback)['OUTPUT']
                requireMergeBufferList.append(uwrOnly_new_uniField_buffDist)

                feedback.setProgressText(f'{uwrOnly_new_uniField_buffDist} created')

                # ==============================================================
                # Append uwr into the final geopackage or create a new one
                # ==============================================================
                if uwrBuffered_exist:
                    requireMergeBufferList.append(uwrBuffered_layer)
                    final = processing.run("native:mergevectorlayers",
                                           {'LAYERS': requireMergeBufferList,
                                            'OUTPUT': uwrBufferedPath + '_updated'})['OUTPUT']
                    os.remove(uwrBufferedPath + '.gpkg')
                    os.rename(final, uwrBufferedPath + '.gpkg')
                    feedback.setProgressText('final geopackage exists')
                else:
                    final = processing.run("native:mergevectorlayers",
                                           {'LAYERS': requireMergeBufferList,
                                            'OUTPUT': uwrBufferedPath})['OUTPUT']
                    for f in requireMergeBufferList:
                        feedback.setProgressText(f'{f} merged')


            else:
                feedback.setProgressText(f'No Need to create uwr buffers')

        except:
            feedback.setProgressText('Something is wrong')

        finally:
            shutil.rmtree(delFolder)
            feedback.setProgressText(f'{delFolder} deleted')
            feedback.setProgressText('Completed')


        # ===========================================================================
        # Calculate the uwr_unique_id field value
        # ===========================================================================

        total = 100.0 / origUWR_source.featureCount() if origUWR_source.featureCount() else 0
        features = origUWR_source.getFeatures()

        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break

            # Update the progress bar
            feedback.setProgress(int(current * total))

        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.

        return  {'uwrBuffered': final}


    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Create UWR buffer'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return '2023_Project'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return createUWRBuffer()


class flightPathConvert(QgsProcessingAlgorithm):
    """
    This is an example algorithm that takes a vector layer and
    creates a new identical one.

    It is meant to be used as an example of how to create your own
    algorithms and explain methods and variables used to do it. An
    algorithm like this will be available in all elements, and there
    is not need for additional work.

    All Processing algorithms should extend the QgsProcessingAlgorithm
    class.
    """

    # Constants used to refer to parameters and outputs. They will be
    # used when calling the algorithm from another algorithm, or when
    # calling from the QGIS console.
    projectFolder = 'projectFolder'
    gpxFolder = 'gpxFolder'
    uwrBuffered = 'uwrBuffered'
    unit_id = 'unit_id'
    unit_id_no = 'unit_id_no'
    DEM = 'DEM'

    def initAlgorithm(self, config):
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        # ===========================================================================
        # Project Folder
        # ===========================================================================
        self.addParameter(QgsProcessingParameterFile(
            self.projectFolder, self.tr('Project Folder'), QgsProcessingParameterFile.Folder, defaultValue='C:\LWRSProject_QGIS\Buffer'))
        # ===========================================================================
        # uwrBuffered
        # ===========================================================================
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.uwrBuffered, self.tr('Input uwrBuffered'), [QgsProcessing.TypeVectorPolygon],defaultValue='C:/LWRSProject_QGIS/Buffer/uwrBuffered_updated.gpkg|layername=uwrBuffered_updated'))

        # ===========================================================================
        # gpx - Input Folder
        # will loop through all the gpx files under the folder
        # ===========================================================================
        self.addParameter(QgsProcessingParameterFile(
            self.gpxFolder, self.tr('Input gpx folder'), QgsProcessingParameterFile.Folder, defaultValue='C:\\LWRSProject_QGIS\\mountaingoatflightlinesamplegpxfiles'))

        # ===========================================================================
        # unit_id / unit_id_no - Input string
        # User selects from the field list derived from OrigUWR
        # ===========================================================================
        self.addParameter(QgsProcessingParameterField(
            self.unit_id, self.tr('Input unit id field, column has text like u-2-002'), 'unit_id', self.uwrBuffered))

        self.addParameter(QgsProcessingParameterField(
            self.unit_id_no, self.tr('Input unit id field, column has text like Mg-059'), 'unit_id_no', self.uwrBuffered))

        # ===========================================================================
        # DEM
        # ===========================================================================
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.DEM, self.tr('Input the project DEM'), 'C:/LWRSProject_QGIS/origDEM/origDEM/project_dem_Clip.tif'))

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """
        # Retrieve the feature source and sink. The 'dest_id' variable is used
        # to uniquely identify the feature sink, and must be included in the
        # dictionary returned by the processAlgorithm function.
        projectFolder = parameters['projectFolder']
        uwrBuffered = self.parameterAsSource(parameters, self.uwrBuffered, context)
        uwrBufferedPath = parameters['uwrBuffered']
        gpxFolder = parameters['gpxFolder']
        DEM = self.parameterAsSource(parameters, self.DEM,context)
        IncursionSeverity = {0: "In UWR", 500: "High", 1000: "Moderate", 1500: "Low"}
        feedback.setProgressText(str(uwrBuffered))

        # ==============================================================
        # unit_no, eg. u-2-002
        # unit_no_id, eg. Mg-106
        # unit_unique_field, field that combines uwr number and uwr unit number
        # ==============================================================
        unit_no = parameters['unit_id']
        unit_no_id = parameters['unit_id_no']
        uwr_unique_Field = "uwr_unique_id"

        # ==============================================================
        # Create variables for converting all gpx files into fc
        # timeIntervalDict - dictionary of different time intervals and the flight points in each
        # flightLines - lists of flight lines
        # flightCount - count of flight lines
        # totalSeasonTime- total flight time in the season
        # checkFilesList - checkFilesList
        # ==============================================================
        timeIntervalDict = {}
        flightLines = []
        flightCount = 0
        totalSeasonTime = 0
        checkFilesList = []

        # ===========================================================================
        # Loop through the input GPX folder and get the row counts
        # ===========================================================================
        gpxFiles = glob.glob(os.path.join(gpxFolder, "*.gpx"))
        count = 0
        gpxTemps = []
        for gpxFile in gpxFiles:
            count += 1
            feedback.setProgressText(f'{str(count)}: {str(gpxFile)}')
            gpxFormattedName = replaceNonAlphaNum(Path(gpxFile).stem, '_')
            feedback.setProgressText(f'{gpxFormattedName}')

            gpxDict = {'tkpt': '|layername=track_points', 'tkline': '|layername=tracks'}
            rowCount = processing.run("qgis:basicstatisticsforfields",
                                      {'INPUT_LAYER': gpxFile + gpxDict['tkpt'],
                                       'FIELD_NAME': 'time',
                                       'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT'})['COUNT']
            tkLyr = QgsVectorLayer((gpxFile + gpxDict['tkline']), "", "ogr")
            tkLyrNameIndex = (tkLyr.fields().names()).index('name')
            if tkLyrNameIndex != None:
                tkLyrFeatures = tkLyr.getFeatures()
                for feature in tkLyrFeatures:
                    tkLyrName = str(feature.attributes()[tkLyrNameIndex])
                    feedback.setProgressText(f'{tkLyrName}')
            feedback.setProgressText(f'{rowCount}')

            # ==============================================================
            # Checks for files with consistent time intervals.
            #  - All fc with same time intervals are grouped together in the dictionary
            #  - If there are more than 2 rows
            #       - find time between point recorded halfway through the flight and the point recorded right before it.
            #       - else,time for objectid 3 - objectid 2 because there was an instance where there were 4 minutes between id 1 and 2.
            #         assume only seconds between them the two points
            # ==============================================================
            if int(rowCount) > 2:
                half = round(int(rowCount) / 2)
                sel = (half - 1, half)
                query = "OBJECTID in " + str(sel)

                tkptLyr_id = processing.run("native:fieldcalculator",
                                         {'FIELD_LENGTH': 100,
                                          'FIELD_NAME': 'OBJECTID',
                                          'NEW_FIELD': True,
                                          'FIELD_PRECISION': 0,
                                          'FIELD_TYPE': 0,
                                          'FORMULA': '@id',
                                          'INPUT': gpxFile + gpxDict['tkpt'],
                                          'OUTPUT': os.path.join(projectFolder, 'tkptLy5rID')})['OUTPUT']
                tkptLyrExtracted = processing.run("native:extractbyexpression",
                                                {'EXPRESSION': query,
                                                 'INPUT': tkptLyr_id,
                                                 'OUTPUT': os.path.join(projectFolder, 'Extracted')})['OUTPUT']
                tkptLyr = QgsVectorLayer((tkptLyrExtracted), "", "ogr")
                tkptExtractedTimeIndex = (tkptLyr.fields().names()).index('time')
                feedback.setProgressText(f'{tkptExtractedTimeIndex}')
                features = tkptLyr.getFeatures()
                values = []
                count = 0
                for f in features:
                    count += 1
                    timeValue = f.attributes()[tkptExtractedTimeIndex]
                    values.append(timeValue)
                timeInterval = values[1].toTime_t() - values[0].toTime_t()
                feedback.setProgressText(f'{timeInterval}')
                feedback.setProgressText(f'{count}')


            else:

                continue
            # ===========================================================================
            # Add the Name field from tracks layer to track points layer
            # ===========================================================================
            gpxTempPath = os.path.join(projectFolder, 'temp_' + gpxFormattedName)
            feedback.setProgressText(f'{gpxTempPath}')
            gpxTemp_saved = processing.run("native:savefeatures",
                                           {'INPUT': gpxFile + gpxDict['tkpt'],
                                            'OUTPUT': 'TEMPORARY_OUTPUT',
                                            'LAYER_NAME': '',
                                            'DATASOURCE_OPTIONS': '',
                                            'LAYER_OPTIONS': ''})['OUTPUT']

            gpxTemp = processing.run("native:fieldcalculator",
                                   {'FIELD_LENGTH': 100,
                                    'FIELD_NAME': 'name_new',
                                    'NEW_FIELD': True,
                                    'FIELD_PRECISION': 0,
                                    'FIELD_TYPE': 2,
                                    'FORMULA':  f"'{tkLyrName}'",
                                    'INPUT': gpxTemp_saved,
                                    'OUTPUT': gpxTempPath}, context=context, feedback=feedback)['OUTPUT']

            gpxTemps.append(gpxTemp)
            feedback.setProgressText(f'{gpxTemps}')


        mergedGPX = os.path.join(projectFolder, 'mergedGPX')
        gpxMerged = processing.run("native:mergevectorlayers",
                                    {'LAYERS': gpxTemps,
                                     'CRS': None,
                                     'OUTPUT': mergedGPX})['OUTPUT']
        rowCount = processing.run("qgis:basicstatisticsforfields",
                                  {'INPUT_LAYER': gpxMerged,
                                   'FIELD_NAME': 'time',
                                   'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT'})['COUNT']
        feedback.setProgressText(f'{rowCount}')





        total = 100.0 / uwrBuffered.featureCount() if uwrBuffered.featureCount() else 0
        features = uwrBuffered.getFeatures()

        for current, feature in enumerate(features):
            # Stop the algorithm if cancel button has been clicked
            if feedback.isCanceled():
                break

            # Update the progress bar
            feedback.setProgress(int(current * total))

        # Return the results of the algorithm. In this case our only result is
        # the feature sink which contains the processed features, but some
        # algorithms may return multiple feature sinks, calculated numeric
        # statistics, etc. These should all be included in the returned
        # dictionary, with keys matching the feature corresponding parameter
        # or output names.

        return

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Flightpath conversion'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr(self.name())

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr(self.groupId())

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return '2023_Project'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return flightPathConvert()
