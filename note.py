for bufferDist in sortBufferDistList:
    ToEraseLoc = rawBufferDict[bufferDist][0]
    ToEraseName = rawBufferDict[bufferDist][1] + '.gpkg'
    ToErasePath = os.path.join(ToEraseLoc, ToEraseName)
    feedback.setProgressText(f'{ToEraseLoc} and {ToEraseName}')
    feedback.setProgressText(f'{bufferDist} -- Bufferdist')

    if sortBufferDistList.index(bufferDist) == 0:
        UseToErasePath = dissolvedOrig_fid_removed
        useToEraseLyr = processing.run("native:savefeatures",
                                       {'INPUT': UseToErasePath,
                                        'OUTPUT': 'TEMPORARY_OUTPUT',
                                        'LAYER_NAME': '',
                                        'DATASOURCE_OPTIONS': '',
                                        'LAYER_OPTIONS': ''}, context=context, feedback=feedback)['OUTPUT']
        useToEraseLyr_saved = QgsVectorLayer((useToEraseLyr), "", "ogr")

        ToEraseLyr = processing.run("native:savefeatures",
                                    {'INPUT': ToErasePath,
                                     'OUTPUT': 'TEMPORARY_OUTPUT',
                                     'LAYER_NAME': '', 'DATASOURCE_OPTIONS': '',
                                     'LAYER_OPTIONS': ''}, context=context, feedback=feedback)['OUTPUT']
        ToEraseLyr_saved = QgsVectorLayer((ToEraseLyr), "", "ogr")

        # count of features
        out_count = 0

        # list of erased fc to merge together
        bufferedFeatures = []

        # select unique id in each fc and erase area of second fc from first fc. Creates a fc output
        for feature in useToEraseLyr_saved.getFeatures():
            useToEraseLyr_fields = useToEraseLyr_saved.fields().names()
            uniqueIDFields_Index = [useToEraseLyr_fields.index(unit_no), useToEraseLyr_fields.index(unit_no_id)]
            unit_no_attribute = feature.attributes()[uniqueIDFields_Index[0]]
            if type(unit_no_attribute) == int:
                expression = '(\"' + uniqueIDFields[0] + '\" = ' + str(
                    feature.attributes()[uniqueIDFields_Index[0]]) + ')'
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

            out_features = projectFolder + "\\outfeature" + str(out_count)
            processing.run("native:difference", {'INPUT': ToEraseLyr_selected,
                                                 'OVERLAY': useToEraseLyr_selected,
                                                 'OUTPUT': out_features, 'GRID_SIZE': None})

            bufferedFeatures.append(out_features + '.gpkg|layername=' + "outfeature" + str(out_count))
            if (out_count % 250) == 0:
                feedback.setProgressText(f'{out_count} features done')

        # merge all outputs
        outputPath = ToEraseLoc + "\\" + ToEraseName + "Only"
        processing.run("native:mergevectorlayers", {'LAYERS': bufferedFeatures,
                                                    'OUTPUT': outputPath})



