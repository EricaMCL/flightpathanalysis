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


def appendMergeFeatures(featuresList, finalPath):
    """
    Purpose:
    When the final feature class does not exist, the list of features will be merged.
    If the final feature class exists, the list of features will be appended.

    Note: if the final feature class exists, it assumes the list of features follow
    the same schema as the final feature class.

    Input:
    featuresList: List of feature classes
    finalPath: Full path of final feature class
    """
    if not arcpy.Exists(finalPath):  # if feature class not exist
        print('need to make', finalPath)
        path = os.path.normpath(finalPath)
        pathSplit = path.split(os.sep)

        for s in pathSplit:
            if '.gdb' in s:
                indexGDB = pathSplit.index(s)
                gdbPathList = pathSplit[:indexGDB + 1]
                gdbPath = os.path.join(*gdbPathList)
                if ':' in pathSplit[0]:
                    gdbPath = gdbPath.replace(":", ":\\")
                else:
                    gdbPath = r"\\" + gdbPath
                break

        # make gdb if not exist
        if not arcpy.Exists(gdbPath):  # if gdb of finalPath not exist
            gdbFolderList = pathSplit[:indexGDB]
            gdbFolder = r"\\" + os.path.join(*gdbFolderList)
            arcpy.CreateFileGDB_management(gdbFolder, pathSplit[indexGDB])
            print("created", pathSplit[indexGDB], "in", gdbFolder)
            print('made gdb', gdbPath)

        # make dataset if not exist
        datasetPathList = pathSplit[:indexGDB + 2]
        datasetPath = r"\\" + os.path.join(*datasetPathList)
        if '.gdb' not in pathSplit[-2]:
            arcpy.CreateFeatureDataset_management(gdbPath, r"\\" + pathSplit[indexGDB + 1])
            print('made', datasetPath)

        # merge all features to final layer
        arcpy.Merge_management(featuresList, finalPath)
        print('made final layer', finalPath)

    else:
        # append all new features into old layer
        arcpy.Append_management(featuresList, finalPath)
        print('appended all features to the final layer', finalPath)


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


def findBufferRange(ToEraseLoc, ToEraseName, UsetoErasePath, uniqueUWR_IDFields, outputGDB):
    """
    (string, string, string, string, string) -> None
    ToEraseLoc: Folder of feature class to be erased
    ToEraseName: Name of feature class to be erased
    UsetoErasePath: Full path location of feature class used to erase the incoming feature class
    uniqueUWR_IDFields: List of unique ID fields of the incoming feature class used to identify for erasing. Has to be a list!!
    outputGDB: Gdb for the output

    Given two feature classes with the same unique field, erase area in each feature in the first
    feature class according to the area of the matching id in the other feature class.

    Returns name of full path to feature class of results of erase analysis
    Output: feature class of erase analysis

    Note: Time used to erase ~3 seconds/record, ~10 min to merge a 1500 record uwr

    """

    print("Erasing starting...Start time: ", datetime.datetime.now())
    starttime = datetime.datetime.now()

    with tempfile.TemporaryDirectory() as temp_location:
        # create temp gdb to store each fc output from erasing with each feature
        tempgdbName = str(ToEraseName) + ".gdb"
        tempgdbPath = temp_location + "\\" + tempgdbName
        arcpy.CreateFileGDB_management(temp_location, tempgdbName)

        arcpy.env.workspace = tempgdbPath
        arcpy.env.overwriteOutput = True

        arcpy.MakeFeatureLayer_management(UsetoErasePath, "UsetoEraseFL")
        arcpy.MakeFeatureLayer_management(os.path.join(ToEraseLoc, ToEraseName), "ToEraseFL")

        # count of features
        out_count = 0

        # list of erased fc to merge together
        bufferedFeatures = []

        # select unique id in each fc and erase area of second fc from first fc. Creates a fc output

        with arcpy.da.SearchCursor("UsetoEraseFL", uniqueUWR_IDFields) as cursor:
            for row in cursor:
                # for field in uniqueUWR_IDFields or i in index

                if type(row[0]) == int:  # if id field is integer
                    query = '(\"' + uniqueUWR_IDFields[0] + '\" = ' + str(row[0]) + ')'
                else:
                    query = '(\"' + uniqueUWR_IDFields[0] + '\" = \'' + str(row[0]) + "')"

                countField = len(uniqueUWR_IDFields)
                if countField > 1:
                    for i in range(1, countField):
                        if type(row[i]) == int:  # if id field is integer
                            query += 'AND (\"' + uniqueUWR_IDFields[i] + '\" = ' + str(row[i]) + ')'
                        else:
                            query += 'AND (\"' + uniqueUWR_IDFields[i] + '\" = \'' + str(row[i]) + "')"

                out_count += 1
                out_features = arcpy.env.workspace + "\\outfeature" + str(out_count)
                arcpy.SelectLayerByAttribute_management("UsetoEraseFL", "NEW_SELECTION", query)
                arcpy.SelectLayerByAttribute_management("ToEraseFL", "NEW_SELECTION", query)
                arcpy.Erase_analysis("ToEraseFL", "UsetoEraseFL", out_features)
                bufferedFeatures.append(out_features)
                if (out_count % 250) == 0:
                    print(out_count, "features done")
        del cursor

        arcpy.Delete_management("UsetoEraseFL")
        arcpy.Delete_management("ToEraseFL")

        print("Runtime to erase: ", datetime.datetime.now() - starttime, ". Merging them now")

        currenttime = datetime.datetime.now()

        arcpy.env.workspace = outputGDB
        arcpy.env.overwriteOutput = True

        # merge all outputs
        outputPath = ToEraseLoc + "\\" + ToEraseName + "Only"
        arcpy.Merge_management(bufferedFeatures, outputPath)

        print("Runtime to merge: ", datetime.datetime.now() - currenttime)

        arcpy.ClearWorkspaceCache_management()  # bug in arcpro 2.6.1. Creating gdb will create lock. This clears it
        print("Total runtime to find buffer range for", ToEraseName, ":", datetime.datetime.now() - starttime)
    return outputPath

##functions for terrain masking
##just use this function to create viewshed
def makeViewshed(uwrList, uwr_bufferFC, buffDistance, unit_no_Field, unit_no_id_Field, uwr_unique_Field, tempGDBPath,
                 DEM, viewshed, minElevViewshed):
    """
    (list, string, integer, string, string, string, optional: string) -> None
    uwrList: List of uwr to make viewsheds for each uwr
    uwr_bufferFC: Feature class of uwr with buffers
    buffDistance: Maximum buffer distance
    unit_no_Field: field for unit number (eg. u-2-002)
    unit_no_id_Field: field for unit number id (eg. TO 32)
    uwr_unique_Field: field made in the buffered_uwr layer and viewshed layer that is a combo of unit_no and unit_no_id
    tempGDBPath: Gdb to store intermediate files
    DEM: Raster DEM
    viewshed: Existing viewshed layer or path to a new viewshed layer
    minElevViewshed: Existing min Elevation viewshed layer or path to a new layer. This contains the minimum elevation required for current ground level areas not visible to be visible

    Purpose: For each uwr in the list of uwr, create a viewshed layer and another viewshed layer
    with minimum height required for objects in currently non visible areas to be visible.
    If the viewshed feature class exists, the new viewsheds created will be appended to them.

    Note: requires 3D and spatial analyst extension to be turned on

    """

    arcpy.env.workspace = tempGDBPath
    arcpy.env.overwriteOutput = True

    UWR_noBuffer = "UWR_noBuffer"
    UWRVertices = "UWRVertices"
    UWR_Buffer = "UWR_Buffer"

    # name of feature layers
    UWR_noBuffer_FL = "UWR_noBuffer_FL"
    UWRVertices_FL = "UWRVertices_FL"
    UWR_Buffer_FL = "UWR_Buffer_FL"
    UWR_DEMPoints_FL = "UWR_DEMPoints_FL"
    polygonViewshed_FL = "polygonViewshed_FL"
    polygon_aglViewshed_FL = "polygon_aglViewshed_FL"

    starttime = datetime.datetime.now()
    # make feature class with relevant UWR - 0m buffer
    uwrSet_str = "','".join(uwrList)

    arcpy.FeatureClassToFeatureClass_conversion(uwr_bufferFC, tempGDBPath, UWR_noBuffer,
                                                uwr_unique_Field + r" in ('" + uwrSet_str + r"') and BUFF_DIST = 0")

    ##subprocess.run(["cscript", r""])

    arcpy.MakeFeatureLayer_management(UWR_noBuffer, UWR_noBuffer_FL)

    # generalize uwr - 0m buffer
    arcpy.Generalize_edit(UWR_noBuffer)

    # convert uwr polygons to vertices
    arcpy.FeatureVerticesToPoints_management(UWR_noBuffer, UWRVertices)

    # get DEM of vertices
    arcpy.sa.ExtractMultiValuesToPoints(UWRVertices, [[DEM, "DEMElev"]])
    arcpy.MakeFeatureLayer_management(UWRVertices, UWRVertices_FL)

    # make feature class with relevant UWR buffered. includes all buffer distances
    arcpy.FeatureClassToFeatureClass_conversion(uwr_bufferFC, tempGDBPath, UWR_Buffer,
                                                uwr_unique_Field + " in ('" + uwrSet_str + "')")  # and BUFF_DIST = " + str(buffDistance)
    arcpy.MakeFeatureLayer_management(UWR_Buffer, UWR_Buffer_FL)
    print("Runtime to make feature layer of uwr - buffer: ", datetime.datetime.now() - starttime)

    # uwrViewshedList = []
    # agl_uwrViewshedList = []

    for uwr in uwrList:
        uwrstarttime = datetime.datetime.now()
        name_uwr = replaceNonAlphaNum(uwr, "_")
        rasterViewshed = "rasterViewshed_" + name_uwr
        agl_rasterViewshed = "agl_rasterViewshed" + name_uwr
        polygonViewshed = "polygonViewshed_" + name_uwr
        totalViewshed = "totalViewshed_" + name_uwr
        totalViewshed_dis = totalViewshed + "dis"
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

        ##check to find the right query depending on if uwr fields are integer or text
        with arcpy.da.SearchCursor(UWR_Buffer_FL, [unit_no_Field, unit_no_id_Field]) as cursor:
            for row in cursor:
                if type(row[0]) == int:  # if unit_no_Field field is integer
                    uwrQuery = '(\"' + unit_no_Field + '\" = ' + uwr_no + ')'
                else:
                    uwrQuery = '(\"' + unit_no_Field + '\" = \'' + uwr_no + "')"

                if type(row[1]) == int:  # if unit_no_id_Field field is integer
                    uwrQuery += ' AND (\"' + unit_no_id_Field + '\" = ' + uwr_no_id + ')'
                else:
                    uwrQuery += ' AND (\"' + unit_no_id_Field + '\" = \'' + uwr_no_id + "')"
                break
        print("working on", uwr)

        viewshedstarttime = datetime.datetime.now()

        # select uwr
        arcpy.SelectLayerByAttribute_management(UWR_Buffer_FL, "NEW_SELECTION", uwrQuery)

        # get extent of biggest uwr buffer to clip raster and get all incursion raster area (uwr+buffer)
        with arcpy.da.SearchCursor(UWR_Buffer_FL, ['SHAPE@'], "BUFF_DIST = " + str(buffDistance)) as cursor:
            for row in cursor:
                extent = row[0].extent
                UWR_Buffer_ExtentList = [str(extent.XMin), str(extent.YMin), str(extent.XMax), str(extent.YMax)]
                UWR_Buffer_Extent = " ".join(UWR_Buffer_ExtentList)
                break
        del cursor

        # clip DEM to uwr + biggest buffer size
        arcpy.Clip_management(DEM, UWR_Buffer_Extent, BufferUWR_DEMClip, in_template_dataset=UWR_Buffer_FL,
                              clipping_geometry='ClippingGeometry', maintain_clipping_extent='NO_MAINTAIN_EXTENT')

        # get extent of original uwr to clip raster and get uwr raster area
        arcpy.SelectLayerByAttribute_management(UWR_Buffer_FL, "NEW_SELECTION", uwrQuery + " and (BUFF_DIST = 0)")
        with arcpy.da.SearchCursor(UWR_Buffer_FL, ['SHAPE@']) as cursor:
            for row in cursor:
                extent = row[0].extent
                UWR_Buffer_ExtentList = [str(extent.XMin), str(extent.YMin), str(extent.XMax), str(extent.YMax)]
                UWR_Buffer_Extent = " ".join(UWR_Buffer_ExtentList)
                break
        del cursor

        # clip dem to buffer - 0m
        arcpy.Clip_management(DEM, UWR_Buffer_Extent, UWR_DEMClip, in_template_dataset=UWR_Buffer_FL,
                              clipping_geometry='ClippingGeometry', maintain_clipping_extent='NO_MAINTAIN_EXTENT')

        # convert raster to points
        arcpy.RasterToPoint_conversion(UWR_DEMClip, UWR_DEMPoints)  # uwr DEM
        arcpy.AlterField_management(UWR_DEMPoints, "grid_code", "DEMElev", "DEMElev")

        arcpy.SelectLayerByAttribute_management(UWRVertices_FL, "NEW_SELECTION", uwrQuery)

        # get list of DEM values for uwr vertices
        DEMvalues = [row[0] for row in arcpy.da.SearchCursor(UWRVertices_FL, "DEMElev") if row[0] is not None]

        # get min value of vertices DEM list
        minValue = min(DEMvalues)

        # get raster DEM values in uwr that are higher than the min DEM value of vertices
        arcpy.MakeFeatureLayer_management(UWR_DEMPoints, UWR_DEMPoints_FL)
        arcpy.SelectLayerByAttribute_management(UWR_DEMPoints_FL, "NEW_SELECTION", "DEMElev > " + str(minValue))

        # add all higher than min DEM value points to vertices layer
        arcpy.Merge_management([UWR_DEMPoints_FL, UWRVertices_FL], UWR_ViewshedObsPoints)

        # make raster viewshed
        arcpy.Viewshed_3d(BufferUWR_DEMClip, UWR_ViewshedObsPoints, rasterViewshed, out_agl_raster=agl_rasterViewshed)

        # make raster viewshed to polygon and includes actual uwr area into the viewshed
        arcpy.RasterToPolygon_conversion(rasterViewshed, polygonViewshed)
        arcpy.MakeFeatureLayer_management(polygonViewshed, polygonViewshed_FL)
        arcpy.SelectLayerByAttribute_management(polygonViewshed_FL, "NEW_SELECTION",
                                                "gridcode <> 0")  # select all direct viewshed area
        arcpy.SelectLayerByAttribute_management(UWR_noBuffer_FL, "NEW_SELECTION",
                                                uwrQuery)  # note: generalized polygon. if want actual area, will need original UWR
        arcpy.Merge_management([polygonViewshed_FL, UWR_noBuffer_FL], totalViewshed)
        arcpy.Dissolve_management(totalViewshed, totalViewshed_dis)

        # label viewshed with uwr name
        arcpy.AddFields_management(totalViewshed_dis,
                                   [[unit_no_Field, "TEXT"], [unit_no_id_Field, "TEXT"], [uwr_unique_Field, "TEXT"]])
        with arcpy.da.UpdateCursor(totalViewshed_dis, [unit_no_Field, unit_no_id_Field, uwr_unique_Field]) as cursor:
            for row in cursor:
                row[0] = uwr_no
                row[1] = uwr_no_id
                row[2] = uwr
                cursor.updateRow(row)
        del cursor

        # convert float agl viewshed raster to integer raster. Convert it to a polygon
        arcpy.ddd.Int(agl_rasterViewshed, int_aglViewshed)
        arcpy.conversion.RasterToPolygon(int_aglViewshed, polygon_aglViewshed, "SIMPLIFY", "Value",
                                         "MULTIPLE_OUTER_PART", None)

        # all areas in direct viewshed are dissolved
        arcpy.MakeFeatureLayer_management(polygon_aglViewshed, polygon_aglViewshed_FL)
        arcpy.management.SelectLayerByAttribute(polygon_aglViewshed_FL, "NEW_SELECTION", "gridcode <= 0", None)
        arcpy.management.CalculateField(polygon_aglViewshed_FL, "gridcode", "0", "PYTHON3", '', "TEXT")
        arcpy.SelectLayerByAttribute_management(polygon_aglViewshed_FL, "CLEAR_SELECTION")
        arcpy.management.Dissolve(polygon_aglViewshed_FL, dissolved_aglViewshed, "gridcode", None, "MULTI_PART",
                                  "DISSOLVE_LINES")

        # label agl viewshed with uwr name
        arcpy.AddFields_management(dissolved_aglViewshed,
                                   [[unit_no_Field, "TEXT"], [unit_no_id_Field, "TEXT"], [uwr_unique_Field, "TEXT"]])
        with arcpy.da.UpdateCursor(dissolved_aglViewshed,
                                   [unit_no_Field, unit_no_id_Field, uwr_unique_Field]) as cursor:
            for row in cursor:
                row[0] = uwr_no
                row[1] = uwr_no_id
                row[2] = uwr
                cursor.updateRow(row)
        del cursor

        # #list of dissolved viewshed areas
        # uwrViewshedList.append(os.path.join(tempGDBPath, totalViewshed_dis))

        # #list of raster agl viewsheds
        # agl_uwrViewshedList.append(os.path.join(tempGDBPath, dissolved_aglViewshed))

        # print(uwrViewshedList)

        print("Runtime to make viewshed:", uwr, ":", datetime.datetime.now() - viewshedstarttime)

        arcpy.Delete_management(polygon_aglViewshed_FL)
        arcpy.Delete_management(polygonViewshed_FL)
        arcpy.Delete_management(UWR_DEMPoints_FL)

        # append or merge recently made viewsheds together
        appendMergeFeatures([os.path.join(tempGDBPath, totalViewshed_dis)], viewshed)
        appendMergeFeatures([os.path.join(tempGDBPath, dissolved_aglViewshed)], minElevViewshed)

    # delete the feature layers or else there will be locking issues or the temp directory can't be removed
    arcpy.Delete_management(UWR_noBuffer_FL)
    arcpy.Delete_management(UWRVertices_FL)
    arcpy.Delete_management(UWR_Buffer_FL)
