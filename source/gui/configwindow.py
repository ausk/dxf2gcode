# -*- coding: utf-8 -*-

############################################################################
#
#   Copyright (C) 2015
#    Xavier Izard
#
#   This file is part of DXF2GCODE.
#
#   DXF2GCODE is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   DXF2GCODE is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with DXF2GCODE.  If not, see <http://www.gnu.org/licenses/>.
#
############################################################################

"""
@purpose: build a configuration window on top of ConfigObj configfile module.

It aims to be generic and reusable for many configuration windows.

*** Basic usage ***
1) Let's say that your ConfigObj spec file is declared as is:
CONFIG_SPEC = str('''
    [MySection]
    # Comment for the variable below
    my_variable = float(min = 0, max = 360, default = 20)
    ''').splitlines()

2) Declare the corresponding dictionnary
config_widget_dict = {
        'MySection':
        {
            '__section_title__': "My Title",
            'my_variable': CfgDoubleSpinBox("My parameter description),
        },
    }

3) Instanciate the config window:
config_window = ConfigWindow(config_widget_dict, var_dict, configspec, self) #See ConfigObj for var_dict & configspec
config_window.finished.connect(self.updateConfiguration) #Optionnal signal to know when the config has changed

*** List of graphical elements currently supported ***
 - CfgCheckBox(): a basic (possibly tristate) checkbox
 - CfgSpinBox(): a spinbox for int values
 - CfgDoubleSpinBox(): a spinbox for float values
 - CfgLineEdit(): a text input (1 line)
 - CfgListEdit(): a text list input (1 line)
 - CfgComboBox(): a drop-down menu for selecting options
 - CfgTable(): a 2D table with editable text entries
 - CfgTableCustomActions(): specific module based on CfgTable(), for storing custom GCODE
 - CfgTableToolParameters(): specific module based on CfgTable(), for storing mill tools
"""

from __future__ import absolute_import

import sys

import inspect

import os
import pprint
import logging

from globals.configobj.configobj import ConfigObj, flatten_errors
from globals.configobj.validate import Validator
import globals.globals as g
from globals.d2gexceptions import *

from globals.six import text_type
import globals.constants as c

if c.PYQT5notPYQT4:
    from PyQt5.QtWidgets import QTabWidget, QDialog, QDialogButtonBox, QMessageBox, QVBoxLayout, QHBoxLayout, QLayout, QFrame, QGridLayout, QLabel, QLineEdit, QTextEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QPushButton, QAbstractItemView, QWidget, QSizePolicy
    from PyQt5.QtGui import QIcon, QPixmap, QValidator, QRegExpValidator
    from PyQt5.QtCore import QLocale, QRegExp
    from PyQt5 import QtCore, QtGui
else:
    from PyQt4.QtGui import QTabWidget, QDialog, QDialogButtonBox, QMessageBox, QVBoxLayout, QHBoxLayout, QLayout, QFrame, QGridLayout, QLabel, QLineEdit, QTextEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget, QTableWidgetItem, QPushButton, QAbstractItemView, QWidget, QSizePolicy, QIcon, QPixmap, QValidator, QRegExpValidator
    from PyQt4.QtCore import QLocale, QRegExp
    from PyQt4 import QtCore


logger = logging.getLogger("Gui.ConfigWindow")


class ConfigWindow(QDialog):
    Applied = QDialog.Accepted + QDialog.Rejected + 1 #Define a result code that is different from accepted and rejected
    
    """Main Class"""
    def __init__(self, definition_dict, config = None, configspec = None, parent = None):
        """
        Initialization of the Configuration window. ConfigObj must be instanciated before this one.
        @param definition_dict: the dict that describes our window
        @param config: data readed from the configfile. This dict is created by ConfigObj module.
        @param configspec: specifications of the configfile. This variable is created by ConfigObj module.
        """
        QDialog.__init__(self, parent)
        self.setWindowTitle("Configuration")

        self.cfg_window_def = definition_dict #This is the dict that describes our window
        self.var_dict = config #This is the data from the configfile (dictionary created by ConfigObj class)
        self.configspec = configspec #This is the specifications for all the entries defined in the config file
        
        #Create the config window according to the description dict received
        config_widget = self.createWidgetFromDefinitionDict()
        
        #Create 3 buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        button_box.accepted.connect(self.accept) #OK button
        button_box.rejected.connect(self.reject) #Cancel button
        apply_button = button_box.button(QDialogButtonBox.Apply)
        apply_button.clicked.connect(self.applyChanges) #Apply button
        
        #Layout the 2 above widgets vertically
        v_box = QVBoxLayout(self)
        v_box.addWidget(config_widget)
        v_box.addWidget(button_box)
        self.setLayout(v_box)
        
        #Populate our Configuration widget with the values from the config file
        self.setValuesFromConfig(self.cfg_window_def, self.var_dict, self.configspec)

    def tr(self, string_to_translate):
        """
        Translate a string using the QCoreApplication translation framework
        @param: string_to_translate: a unicode string
        @return: the translated unicode string if it was possible to translate
        """
        return text_type(QtCore.QCoreApplication.translate('ConfigWindow', string_to_translate))

    def accept(self):
        """
        Check and apply the changes, then close the config window (OK button)
        """
        ok, errors_list = self.validateConfiguration(self.cfg_window_def)
        if ok:
            self.updateConfiguration(self.cfg_window_def, self.var_dict) #Update the configuration dict according to the new settings in our config window
            QDialog.accept(self)
            logger.info('New configuration OK')
        else:
            self.displayMessageBox(errors_list)

    def applyChanges(self):
        """
        Apply changes without closing the window (allow to test some changes without reopening the config window each time)
        """
        ok, errors_list = self.validateConfiguration(self.cfg_window_def)
        if ok:
            self.updateConfiguration(self.cfg_window_def, self.var_dict) #Update the configuration dict according to the new settings in our config window
            self.setResult(ConfigWindow.Applied) #Return a result code that is different from accepted and rejected
            self.finished.emit(self.result())
            logger.info('New configuration applied')
        else:
            self.displayMessageBox(errors_list)

    def reject(self):
        """
        Reload our configuration widget with the values from the config file (=> Cancel the changes in the config window), then close the config window
        """
        self.setValuesFromConfig(self.cfg_window_def, self.var_dict, self.configspec)
        QDialog.reject(self)
        logger.info('New configuration cancelled')


    def displayMessageBox(self, errors_list):
        """
        Popup a message box in order to display an error message
        @param errors_list: a string that contains all the errors
        """
        errors_list = self.tr('Please correct the following error(s):\n') + errors_list
        error_message = QMessageBox(QMessageBox.Critical, self.tr('Invalid changes'), errors_list);
        error_message.exec_()


    def createWidgetFromDefinitionDict(self):
        """
        Automatically build a widget, based on dict definition of the items.
        @return: a QWidget containing all the elements of the configuration window
        """
        logger.info('Creating configuration window')
        tab_widget = QTabWidget()
        definition = self.cfg_window_def
        
        #Create a dict with the sections' titles if not already defined. This dict contains sections' names as key and tabs' titles as values
        if '__section_title__' not in definition:
            definition['__section_title__'] = {}

        #Compute all the sections
        for section in sorted(definition):
            #skip the special section __section_title__
            if section == '__section_title__':
                continue
            
            #Create the title for the section if it doesn't already exist
            if section not in definition['__section_title__']:
                #The title for this section doesn't exist yet
                if isinstance(definition[section], dict) and '__section_title__' in definition[section]:
                    #The title for this section is defined into the section itself => we add the title to the dict containing all the titles
                    definition['__section_title__'][section] = definition[section]['__section_title__']
                else:
                    #The title for this section is not defined anywhere, so we use the section name itself as a title
                    definition['__section_title__'][section] = section.replace('_', ' ')
        
            #Create the tab (and the widget) for the current section, if it doesn't exist yet
            widget = None
            for i in range(tab_widget.count()):
                if definition['__section_title__'][section] == tab_widget.tabText(i):
                    widget = tab_widget.widget(i)
                    break
            
            if widget is None:
                widget = QWidget()
                tab_widget.addTab(widget, definition['__section_title__'][section])
            
            #Create the tab content for this section
            self.createWidgetSubSection(definition[section], widget)
            #Add a separator at the end of this subsection
            if widget.layout() is not None:
                separator = QFrame()
                separator.setFrameShape(QFrame.HLine)
                widget.layout().addWidget(separator)
                widget.layout().addStretch()

        #Add a QSpacer at the bottom of each widget, so that the items are placed on top of each tab
        for i in range(tab_widget.count()):
            if tab_widget.widget(i).layout() is not None:
                tab_widget.widget(i).layout().addStretch()
        
        return tab_widget

    def createWidgetSubSection(self, subdefinition, section_widget):
        """
        Create the widgets that will be inserted into the tabs of the configuration window
        @param subdefinition: part of the definition dict
        @param section_widget: the widget that host the subwidgets
        @return: section_widget (for recursive call)
        """
        #section_widget = QWidget()
        vertical_box = section_widget.layout()
        if vertical_box is None:
            vertical_box = QVBoxLayout()
            section_widget.setLayout(vertical_box)
        vertical_box.setSpacing(0) #Don't use too much space, it makes the option window too big otherwise
        
        if isinstance(subdefinition, dict):
            for subsection in sorted(subdefinition):
                if subsection == '__section_title__':
                    #skip the special section
                    continue
                
                #Browse sublevels
                self.createWidgetSubSection(subdefinition[subsection], section_widget) #Recursive call, all the nested configuration item will appear at the same level
        else:
            if isinstance(subdefinition, (QWidget, QLayout)):
                vertical_box.addWidget(subdefinition)
            else:
                #Item should be a layout or a widget
                logger.error("item subdefinition is incorrect")
        
        return section_widget


    def setValuesFromConfig(self, window_def, config, configspec):
        """
        This function populates the option widget with the values that come from the configuration file.
        The values from the configuration file are stored into a dictionary, we browse this dictionary to populate our window
        @param window_def: the dict that describes our window
        @param config: data readed from the configfile. This dict is created by ConfigObj module.
        @param configspec: specifications of the configfile. This variable is created by ConfigObj module.
        """
        #Compute all the sections
        for section in window_def:
            #skip the special section __section_title__
            if section == '__section_title__':
                continue
            
            if config is not None and section in config:
                if isinstance(window_def[section], dict):
                    #Browse sublevels
                    configspec_sub = None
                    if configspec is not None and section in configspec:
                        configspec_sub = configspec[section]
                    self.setValuesFromConfig(window_def[section], config[section], configspec_sub) #Recursive call, until we find a real item (not a dictionnary with subtree)
                else:
                    if isinstance(window_def[section], (QWidget, QLayout)):
                        #assign the configuration retrieved from the configspec object of the ConfigObj
                        if configspec is not None and section in configspec:
                            window_def[section].setSpec(self.configspecParser(configspec[section], configspec.comments[section]))
                        #assign the value that was readed from the configfile
                        window_def[section].setValue(config[section])
                    else:
                        #Item should be a layout or a widget
                        logger.warning("item {0} is not a widget, can't set it's value!".format(window_def[section]))
            else:
                logger.error("can't assign values, item or section {0} not found in config file!".format(section))


    def configspecParser(self, configspec, comments):
        """
        This is a really trivial parser for ConfigObj spec file. This parser aims to exctract the limits and the available options for the entries in the config file. For example:
        if a config entry is defined as "option('mm', 'in', default = 'mm')", then the parser will create a list with ['mm', 'in]
        similarly, if an entry defined as "integer(max=9)", the max value will be exctracted
        @param configspec: specifications of the configfile. This variable is created by ConfigObj module.
        @param comments: string list containing the comments for a given item
        @return The function returns a dictionary with the following fields
        - minimum : contains the minimum value or length for an entry (possibly 'None' if nothing found)
        - maximum : contains the maximum value or length for an entry (possibly 'None' if nothing found)
        - string_list : contains the list of options for an "option" field, or the column titles for a table
        - comment : a text with the comment that belongs to the parameter (possibly an empty string if nothing found)
        """
        #logger.debug('configspecParser({0}, {1})'.format(configspec, comments))
        minimum = None
        maximum = None
        string_list = []
        
        if isinstance(configspec, dict):
            #If the received configspec is a dictionary, we most likely have a table, so we are going to exctract sections names of this table
            
                #When tables are used, the "__many__" config entry is used for the definition of the configspec, so we try to excract the sections names by using this __many__ special keyword.
                #Example: 'Tool_Parameters': {[...], '__many__': {'diameter': 'float(default = 3.0)', 'speed': 'float(default = 6000)', 'start_radius': 'float(default = 3.0)'}}
                if '__many__' in configspec and isinstance(configspec['__many__'], dict):
                    string_list = configspec['__many__'].keys()
                    string_list.insert(0, '') #prepend an empty element since the first column of the table is the row name (eg a unique tool number)
        
        else:
            #configspec is normaly a string from which we can exctrat min / max values and possibly a list of options
            
            #Handle "option" config entries
            string_list = self.configspecParserExctractSections('option', configspec)
            i = 0
            while i < len(string_list): #DON'T replace this with a "for", it would silently skip some steps because we remove items inside the loop
                #if not string_list[i]:
                #	del string_list[i]
                #	continue
                
                #remove leading and trailing spaces
                string_list[i] = string_list[i].strip()
                
                #remove unwanted items which are unquoted (like the "default=" parameter) and remove the quotes
                if string_list[i].startswith('"'):
                    string_list[i] = string_list[i].strip('"')
                elif string_list[i].startswith("'"):
                    string_list[i] = string_list[i].strip("'")
                else:
                    #unwanted item, it doesn't contain an element of the option()
                    del string_list[i]
                    continue
                    
                i += 1
            
            #Handle "integer" and "string" config entries
            if len(string_list) <= 0:
                string_list = self.configspecParserExctractSections('integer', configspec)
                if len(string_list) <= 0:
                    string_list = self.configspecParserExctractSections('string', configspec)
                i = 0
                while i < len(string_list): #DON'T replace this with a "for", it would silently skip some steps because we remove items inside the loop
                    element = string_list[i]
                    #remove empty elements
                    if not element:
                        del string_list[i]
                        continue
                    
                    #remove leading and trailing spaces
                    element = element.strip()
                    
                    if minimum is None:
                        try: minimum = int(element)
                        except ValueError: pass
                    else:
                        if maximum is None:
                            try: maximum = int(element)
                            except ValueError: pass
                    
                    if minimum is None and 'min' in element:
                        #'min' string found in a string like "min = -7"
                        element = element.replace('min', '')
                        element = element.strip(' =')
                        try: minimum = int(element)
                        except ValueError: pass
                    
                    if maximum is None and 'max' in element:
                        #'max' string found
                        element = element.replace('max', '')
                        element = element.strip(' =')
                        try: maximum = int(element)
                        except ValueError: pass
                    
                    i += 1
            
            #Handle "float" config entries
            if len(string_list) <= 0:
                string_list = self.configspecParserExctractSections('float', configspec)
                i = 0
                while i < len(string_list): #DON'T replace this with a "for", it would silently skip some steps because we remove items inside the loop
                    element = string_list[i]
                    #remove empty elements
                    if not element:
                        del string_list[i]
                        continue
                    
                    #remove leading and trailing spaces
                    element = element.strip()
                    
                    if minimum is None:
                        try: minimum = float(element)
                        except ValueError: pass
                    else:
                        if maximum is None:
                            try: maximum = float(element)
                            except ValueError: pass
                    
                    if minimum is None and 'min' in element:
                        #'min' string found in a string like "min = -7"
                        element = element.replace('min', '')
                        element = element.strip(' =')
                        try: minimum = float(element)
                        except ValueError: pass
                    
                    if maximum is None and 'max' in element:
                        #'max' string found
                        element = element.replace('max', '')
                        element = element.strip(' =')
                        try: maximum = float(element)
                        except ValueError: pass
                    
                    i += 1
        
        #Handle comments: comments are stored in a list and contains any chars that are in the configfile (including the hash symbol and the spaces)
        comments_string = ''
        if len(comments) > 0:
            for comment in comments:
                comments_string += comment.strip()
            
            comments_string = comments_string.strip(' #')
            comments_string = comments_string.replace('#', '\n')
        
        logger.debug('configspecParser(): exctracted option elements = {0}, min = {1}, max = {2}, comment = {3}'.format(string_list, minimum, maximum, comments_string))
        
        result = {}
        result['minimum'] = minimum
        result['maximum'] = maximum
        result['string_list'] = string_list
        result['comment'] = comments_string
        return result

    def configspecParserExctractSections(self, attribute_name, string):
        """
        returns a list of item from a string. Eg the string "option('mm', 'in', default = 'mm')" will be exploded into the string list ["mm", "in", "default = 'mm'"]
        """
        string_list = []
        
        pos_init = string.find(attribute_name + '(')
        if pos_init >= 0:
            pos_init += len(attribute_name + '(') #skip the "option("
            
            pos_end = string.find(')', pos_init)
            if pos_end > pos_init:
                #print("substring found = {0}".format(string[pos_init:pos_end]))
                string_list = string[pos_init:pos_end].split(',')
        
        return string_list


    def validateConfiguration(self, window_def, result_string = '', result_bool = True):
        """
        Check the configuration (check the limits, eg min/max values, ...). These limits are set according to the configspec passed to the constructor
        @param window_def: the dict that describes our window
        @param result_string: use only for recursive call
        @param result_bool: use only for recursive call
        @return (result_bool, result_string):
         - result_bool: True if no errors were encountered, False otherwise
         - result_string: a string containing all the errors encountered during the validation
        """
        #Compute all the sections
        for section in window_def:
            #skip the special section __section_title__
            if section == '__section_title__':
                continue
            
            if isinstance(window_def[section], dict):
                #Browse sublevels
                (result_bool, result_string) = self.validateConfiguration(window_def[section], result_string, result_bool) #Recursive call, until we find a real item (not a dictionnary with subtree)
            else:
                if isinstance(window_def[section], (QWidget, QLayout)):
                    #check that the value is correct for each widget
                    result = window_def[section].validateValue()
                    if result[0] is False: result_bool = False
                    result_string += result[1]
                else:
                    #Item should be a layout or a widget
                    logger.warning("item {0} is not a widget, can't validate it!".format(window_def[section]))
        
        return (result_bool, result_string)


    def updateConfiguration(self, window_def, config):
        """
        Update the application configuration (ConfigObj) according to the changes made into the ConfigWindow.
        The self.var_dict variable is updated
        @param window_def: the dict that describes our window
        @param config: data readed from the configfile. This dict is created by ConfigObj module and will be updated here.
        """
        #Compute all the sections
        for section in window_def:
            #skip the special section __section_title__
            if section == '__section_title__':
                continue
            
            if config is not None and section in config:
                if isinstance(window_def[section], dict):
                    #Browse sublevels
                    self.updateConfiguration(window_def[section], config[section]) #Recursive call, until we find a real item (not a dictionnary with subtree)
                else:
                    if isinstance(window_def[section], (QWidget, QLayout)):
                        #assign the value that was readed from the configfile
                        config[section] = window_def[section].getValue()
                    else:
                        #Item should be a layout or a widget
                        logger.warning("item {0} is not a widget, can't update it!".format(window_def[section]))
            else:
                logger.error("can't update configuration, item or section {0} not found in config file!".format(section))



############################################################################################################################
# The classes below are all based on QWidgets and allow to create various predefined elements for the configuration window #
############################################################################################################################

class CfgCheckBox(QCheckBox):
    """
    Subclassed QCheckBox to match our needs.
    """

    def __init__(self, text, tristate = False, parent = None):
        """
        Initialization of the CfgCheckBox class.
        @param text: text string associated with the checkbox
        @param tristate: whether the checkbox must have 3 states (tristate) or 2 states
        """
        QCheckBox.__init__(self, text, parent)
        self.setTristate(tristate)

    def setSpec(self, spec):
        """
        Set the specifications for the item (min/max values, ...)
        @param spec: the specifications dict (can contain the following keys: minimum, maximum, comment, string_list)
        """
        #Nothing is configurable in the configspec for this item
        if spec['comment']:
            self.setWhatsThis(spec['comment'])

    def validateValue(self):
        """
        This item can't be wrong, so we always return true and an empty string
        @return (True, ''):
        """
        return (True, '')

    def getValue(self):
        """
        @return 0 when the checkbox is unchecked, 1 if it is checked and 2 if it is partly checked (tristate must be set to true for tristate mode)
        """
        check_state = self.checkState()
        if check_state == QtCore.Qt.Unchecked:
            check_state = 0
        elif check_state == QtCore.Qt.Checked:
            check_state = 1
        elif check_state == QtCore.Qt.PartiallyChecked:
            check_state = 2
            
        return check_state

    def setValue(self, value):
        """
        Assign the value for our object
        @param value: 0 when the checkbox is unchecked, 1 if it is checked and 2 if it is partly checked (tristate must be set to true for tristate mode)
        """
        if value == 0:
            self.setCheckState(QtCore.Qt.Unchecked)
        elif value == 2:
            self.setCheckState(QtCore.Qt.PartiallyChecked)
        else:
            self.setCheckState(QtCore.Qt.Checked)


class CfgSpinBox(QWidget):
    """
    Subclassed QSpinBox to match our needs.
    """

    def __init__(self, text, unit = None, minimum = None, maximum = None, parent = None):
        """
        Initialization of the CfgSpinBox class (used for int values).
        @param text: text string associated with the SpinBox
        @param minimum: min value (int)
        @param minimum: max value (int)
        """
        QWidget.__init__(self, parent)
        
        self.spinbox = QSpinBox(parent)
        if unit is not None:
            self.setUnit(unit)

        self.setSpec({'minimum': minimum, 'maximum': maximum, 'comment': ''})

        self.label = QLabel(text, parent)
        self.layout = QHBoxLayout(parent);
        
        self.spinbox.setMinimumWidth(200) #Provide better alignment with other items
        self.layout.addWidget(self.label)
        self.layout.addStretch()
        self.layout.addWidget(self.spinbox)
        self.setLayout(self.layout)

    def setSpec(self, spec):
        """
        Set the specifications for the item (min/max values, ...)
        @param spec: the specifications dict (can contain the following keys: minimum, maximum, comment, string_list)
        """
        if spec['minimum'] is not None:
            self.spinbox.setMinimum(spec['minimum'])
        else:
            self.spinbox.setMinimum(-1000000000) #if no value is defined for the minimum, use a reasonable value
        if spec['maximum'] is not None:
            self.spinbox.setMaximum(spec['maximum'])
        else:
            self.spinbox.setMaximum(1000000000) #if no value is defined for the maximum, use a more reasonable value than 99 (default value in QT) ...
        if spec['comment']:
            self.setWhatsThis(spec['comment'])

    def setUnit(self, unit):
        """
        Set the unit of the SpinBox (unit is displayed just after the value)
        @param unit: string with the unit used for the spinbox
        """
        self.spinbox.setSuffix(unit)

    def validateValue(self):
        """
        This item can't be wrong, so we always return true and an empty string
        @return (True, ''):
        """
        return (True, '')

    def getValue(self):
        """
        @return: the current value of the QSpinBox
        """
        return self.spinbox.value()

    def setValue(self, value):
        """
        Assign the value for our object
        @param value: int value
        """
        self.spinbox.setValue(value)


class CorrectedDoubleSpinBox(QDoubleSpinBox):
    """
    Subclassed QDoubleSpinBox to get a version that works for everyone ...
    DON'T remove this class, it is a correction for the guys who decided to use comma (',') as a decimal separator (France, Italy, ...) but failed to use comma on the keypad (keypad use dot, not comma)!
    This subclassed QDoubleSpinBox allow to enter decimal values like 3.5 _and_ 3,5
    (the default QDoubleSpinBox implementation only allow the locale as a decimal separator, so for eg, France, you just can't enter decimal values using the keypad!)
    See here for more details: http://www.qtcentre.org/threads/12483-Validator-for-QDoubleSpinBox and http://www.qtcentre.org/threads/13711-QDoubleSpinBox-dot-as-comma
    """

    def __init__(self, parent = None):
        QDoubleSpinBox.__init__(self, parent)
        self.saved_suffix = ''
        #Let's use the locale decimal separator if it is different from the dot ('.')
        local_decimal_separator = QLocale().decimalPoint()
        if local_decimal_separator == '.':
            local_decimal_separator = ''
        self.lineEdit().setValidator(QRegExpValidator(QRegExp("-?[0-9]*[.{0}]?[0-9]*.*".format(local_decimal_separator)), self))

    def setSuffix(self, suffix):
        self.saved_suffix = suffix
        QDoubleSpinBox.setSuffix(self, suffix)

    def valueFromText(self, text):
        if c.PYQT5notPYQT4:
            #print("valueFromText({0})".format(text.encode('utf-8')))
            text = text.encode('utf-8').replace(self.saved_suffix.encode('utf-8'), '').replace(QLocale().decimalPoint(), '.')
        else:
            #print("valueFromText({0})".format(text))
            text = text.replace(self.saved_suffix, '').replace(QLocale().decimalPoint(), '.')
        try:
            #result = float(text.replace('.', QLocale().decimalPoint()))
            result = float(text) #python expect a dot ('.') as decimal separator
        except ValueError:
            result = 0.0
        return result

    def validate(self, entry, pos):
        #let's *really* trust the validator
        #http://python.6.x6.nabble.com/QValidator-raises-TypeError-td1923683.html
        #print("validate({}, {})".format(entry, pos))
        if c.PYQT5notPYQT4:
            return (QValidator.Acceptable, entry, pos)
        else:
            return (QValidator.Acceptable, pos)


class CfgDoubleSpinBox(CfgSpinBox):
    """
    Subclassed QDoubleSpinBox to match our needs.
    """

    def __init__(self, text, unit = None, minimum = None, maximum = None, precision = None, parent = None):
        """
        Initialization of the CfgDoubleSpinBox class (used for float values).
        @param text: text string associated with the SpinBox
        @param minimum: min value (float)
        @param minimum: max value (float)
        """
        QWidget.__init__(self, parent)
        
        self.spinbox = CorrectedDoubleSpinBox(parent)
        if unit is not None:
            self.setUnit(unit)
        
        self.setSpec({'minimum': minimum, 'maximum': maximum, 'comment': ''})
        
        if precision is not None:
            self.spinbox.setDecimals(precision)

        self.label = QLabel(text, parent)
        self.layout = QHBoxLayout(parent);
        
        self.spinbox.setMinimumWidth(200) #Provide better alignment with other items
        self.layout.addWidget(self.label)
        self.layout.addStretch()
        self.layout.addWidget(self.spinbox)
        self.setLayout(self.layout)


class CfgLineEdit(QWidget):
    """
    Subclassed QLineEdit to match our needs.
    """

    def __init__(self, text, size_min = None, size_max = None, parent = None):
        """
        Initialization of the CfgLineEdit class (text edit, one line).
        @param text: text string associated with the line edit
        @param size_min: min length (int)
        @param size_max: max length (int)
        """
        QWidget.__init__(self, parent)
        
        self.lineedit = QLineEdit(parent)
        
        self.setSpec({'minimum': size_min, 'maximum': size_max, 'comment': ''})
        if size_min is not None:
            self.size_min = size_min
        else:
            self.size_min = 0
        
        self.label = QLabel(text, parent)
        self.layout = QVBoxLayout(parent)
        
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.lineedit)
        self.setLayout(self.layout)
        self.layout.setSpacing(1) #Don't use too much space, it makes the option window too big otherwise

    def setSpec(self, spec):
        """
        Set the specifications for the item (min/max values, ...)
        @param spec: the specifications dict (can contain the following keys: minimum, maximum, comment, string_list)
        """
        if spec['minimum'] is not None:
            self.size_min = spec['minimum']
        
        if spec['maximum'] is not None:
            self.lineedit.setMaxLength(spec['maximum'])
        
        if spec['comment']:
            self.setWhatsThis(spec['comment'])

    def validateValue(self):
        """
        Check the minimum length value
        @return (result_bool, result_string):
         - result_bool: True if no errors were encountered, False otherwise
         - result_string: a string containing all the errors encountered during the validation
        """
        field_length = len(str(self.lineedit.text()))
        if field_length < self.size_min:
            result = (False, str(self.tr('\nNot enough chars (expected {0}, found {1}) for the field "{2}"\n')).format(self.size_min, field_length, self.label.text()))
        else:
            #OK
            result = (True, '')
        return result

    def getValue(self):
        """
        @return: the current value of the QSpinBox
        """
        return str(self.lineedit.text())

    def setValue(self, value):
        """
        Assign the value for our object
        @param value: text string
        """
        self.lineedit.setText(value)


class CfgListEdit(CfgLineEdit):
    """
    Subclassed QLineEdit to match our needs.
    """

    def __init__(self, text, separator, size_max = None, parent = None):
        """
        Initialization of the CfgListEdit class (text edit, one line, strings separated with "separator").
        @param text: text string associated with the line edit
        @param separator: the separator used for the strings (eg: ',')
        @param size_min: min length (int)
        @param size_max: max length (int)
        """
        CfgLineEdit.__init__(self, text + " (use '" + separator + "' as separator)", size_max, parent)
        #Store the separator so that we can return a list of strings instead of a single string
        self.separator = separator

    def getValue(self):
        """
        @return the current value of the QSpinBox (string list)
        """
        item_list = str(self.lineedit.text()).split(self.separator)
        i = 0
        while i < len(item_list):
            item_list[i] = item_list[i].strip(' ') #remove leading and trailing whitespaces
            i += 1
        return item_list

    def setValue(self, value):
        """
        Assign the value for our object
        @param value: text string or list of text strings
        """
        joined_value = value
        if isinstance(value, (list, tuple)):
            joined_value = (self.separator + ' ').join(value) #Join the strings and add a space for more readability (the space will be removed when writting)
        
        self.lineedit.setText(joined_value)



class CfgComboBox(QWidget):
    """
    Subclassed QComboBox to match our needs.
    """

    def __init__(self, text, items_list = None, default_item = None, parent = None):
        """
        Initialization of the CfgComboBox class (drop-down menu).
        @param text: text string associated with the combobox
        @param items_list: string list containing all the available options
        @param default_item: string containing the default selected item
        """
        QWidget.__init__(self, parent)
        
        self.combobox = QComboBox(parent)
        
        if isinstance(items_list, (list, tuple)):
            self.setSpec({'string_list': items_list, 'comment': ''})
        if default_item is not None:
            self.setValue(default_item)
        
        self.label = QLabel(text, parent)
        self.layout = QHBoxLayout(parent);
        
        self.combobox.setMinimumWidth(200) #Provide better alignment with other items
        self.layout.addWidget(self.label)
        self.layout.addStretch()
        self.layout.addWidget(self.combobox)
        self.setLayout(self.layout)

    def setSpec(self, spec):
        """
        Set the specifications for the item (min/max values, ...)
        @param spec: the specifications dict (can contain the following keys: minimum, maximum, comment, string_list)
        """
        self.combobox.clear()
        self.combobox.addItems(spec['string_list'])
        
        if spec['comment']:
            self.setWhatsThis(spec['comment'])

    def validateValue(self):
        """
        This item can't be wrong, so we always return true and an empty string
        @return (True, ''):
        """
        return (True, '')

    def getValue(self):
        """
        @return: the string of the currently selected entry
        """
        return self.combobox.currentText()

    def setValue(self, value):
        """
        Assign the value for our object
        @param value: the text of the entry to select in the combobox
        """
        self.combobox.setCurrentIndex(self.combobox.findText(value)) #Compatible with both PyQt4 and PyQt5


class CfgTable(QWidget):
    """
    Subclassed QTableWidget to match our needs.
    """

    def __init__(self, text, columns = None, parent = None):
        """
        Initialization of the CfgTable class (editable 2D table).
        @param text: text string associated with the table
        @param columns: string list containing all the columns names
        """
        QWidget.__init__(self, parent)
        
        self.tablewidget = QTableWidget(parent)
        self.tablewidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        if isinstance(columns, (list, tuple)):
            self.setSpec({'string_list': columns, 'comment': ''})
        else:
            self.keys = [] #No columns yet
        self.tablewidget.horizontalHeader().setStretchLastSection(True)
        self.tablewidget.horizontalHeader().sectionClicked.connect(self.tablewidget.clearSelection) #Allow to unselect the lines by clicking on the column name (useful to add a line at the end)
        
        self.label = QLabel(text, parent)
        self.button_add = QPushButton(QIcon(QPixmap(":/images/list-add.png")), "")
        self.button_remove = QPushButton(QIcon(QPixmap(":/images/list-remove.png")), "")
        self.button_add.clicked.connect(self.appendLine)
        self.button_remove.clicked.connect(self.removeLine)
        self.layout_button = QVBoxLayout();
        self.layout_button.addWidget(self.button_add)
        self.layout_button.addWidget(self.button_remove)
        
        self.layout_table = QHBoxLayout();
        #self.tablewidget.setSizePolicy(size_policy)
        self.layout_table.addWidget(self.tablewidget)
        self.layout_table.addLayout(self.layout_button)
        
        self.layout = QVBoxLayout(parent);
        
        self.layout.addWidget(self.label)
        self.layout.addLayout(self.layout_table)
        self.setLayout(self.layout)
        
        #Ensure that the table always expand to the maximum available space
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        size_policy.setVerticalStretch(10)
        size_policy.setHorizontalStretch(10)
        self.setSizePolicy(size_policy)

    def setSpec(self, spec):
        """
        Set the specifications for the item (min/max values, ...)
        @param spec: the specifications dict (can contain the following keys: minimum, maximum, comment, string_list)
        """
        self.keys = spec['string_list']
        if len(self.keys) > 0 and not self.keys[0]:
            self.keys[0] = 'name' #name of first column is normaly undefined in configspec, so we use a generic name, just to display something in the header of the QTable
        self.tablewidget.setColumnCount(len(self.keys))
        self.tablewidget.setHorizontalHeaderLabels(self.keys)
        
        if spec['comment']:
            self.setWhatsThis(spec['comment'])

    def appendLine(self, line = None):
        """
        Add a line to the table. The new line is inserted before the selected line, or at the end of the table is no line is selected
        @param line: a string list containing all the values for this lines. If line is None, an empty line is inserted
        """
        selected_row = self.tablewidget.currentRow()
        if selected_row < 0 or len(self.tablewidget.selectedIndexes()) <= 0: #Trick to be able to insert lines before the first and after the last line (click on column name to unselect the lines)
            selected_row = self.tablewidget.rowCount()
            
        self.tablewidget.insertRow(selected_row)
        
        #If provided, fill the table with the content of the line list
        if line is not None and isinstance(line, (list, tuple)) and len(line) >= self.tablewidget.columnCount():
            for i in range(self.tablewidget.columnCount()):
                #self.tablewidget.setItem(selected_row, i, QTableWidgetItem(line[i]))
                self.setCellValue(selected_row, i, line[i])
        else:
            for i in range(self.tablewidget.columnCount()):
                self.setCellValue(selected_row, i, "") #Don't remove this line, otherwise the subclasses won't be able to set custom widget into the table.

        #Resize the columns to the content, except for the last one
        for i in range(self.tablewidget.columnCount() - 1):
            self.tablewidget.resizeColumnToContents(i)

        #Resize the rows to the content
        for i in range(self.tablewidget.rowCount()):
            self.tablewidget.resizeRowToContents(i)

    def removeLine(self):
        """
        Remove a line from the table. The selected line is suppressed, or the last line if no line is selected
        """
        selected_row = self.tablewidget.currentRow()
        if selected_row < 0 and self.tablewidget.rowCount() > 0:
            selected_row = self.tablewidget.rowCount() - 1
            
        if selected_row >= 0:
            self.tablewidget.removeRow(selected_row)

    def setCellValue(self, line, column, value):
        """
        Default implementation for filling cells use Qt default QTableWidgetItem. One can subclass to provide another implementation, like inserting various Widget into the table.
        @param line: line number (int)
        @param column: column number (int)
        @param value: cell content (string)
        """
        self.tablewidget.setItem(line, column, QTableWidgetItem(value))

    def validateValue(self):
        """
        Default implementation always return true (OK) and an empty string
        @return (True, ''):
        """
        return (True, '')

    def getValue(self):
        """
        @return: a nested dictionnary that can be directly used to update the ConfigObj (class that handles configuration file)
        Example of returned value:
        {'pause': {'gcode': 'M5 (Spindle off)\nM9 (Coolant off)\nM0\n\nM8\nS5000M03 (Spindle 5000rpm cw)\n'}, 'probe_tool': {'gcode': '\nO<Probe_Tool> CALL\nS6000 M3 M8\n'}}
        """
        result_dict = {}
        for i in range(self.tablewidget.rowCount()):
            key = self.tablewidget.item(i, 0)
            if not key:
                continue
            key = str(key.text())
            if not key:
                continue
            result_dict[key] = {}
            
            j = 1
            while j < self.tablewidget.columnCount():
                sub_key = self.keys[j] #Column name
                value = self.tablewidget.item(i, j)
                if not value:
                    j += 1
                    continue
                value = str(value.text())
                if sub_key is not None:
                    result_dict[key][sub_key] = value
                j += 1
        
        return result_dict
    
    def setValue(self, value):
        """
        Assign the value for our object
        @param value: this is a nested dict, with keys going to the first column of our table and values going to the other columns. Example of received value:
        {'15': {'diameter': 1.5, 'speed': 6000.0, 'start_radius': 1.5}, '20': {'diameter': 2.0, 'speed': 6000.0, 'start_radius': 2.0}, '30': {'diameter': 3.0, 'speed': 6000.0, 'start_radius': 3.0}}
        """
        result = True
        if isinstance(value, dict) and len(self.keys) > 0:
            self.tablewidget.setRowCount(0)
            line = [None] * len(self.keys)
            
            #sort according to the key
            item_list=[]
            try:
                #try numeric sort
                item_list = sorted(value.keys(), key=float)
            except ValueError:
                #fallback to standard sort
                item_list = sorted(value.keys())
            
            for item in item_list:
                line[0] = item #First column is alway the key of the dict (eg it can be the tool number)
                
                #Compute the other columns (the received value must contain a dict entry for each column)
                i = 1
                while i < len(self.keys):
                    if self.keys[i] in value[item]:
                        line[i] = value[item][self.keys[i]] #Get the value for a given column
                    else:
                        result = False
                        break
                    i += 1
                
                if result is True:
                    self.appendLine(line)
        else:
            result = False
        
        return result


class CfgTableCustomActions(CfgTable):
    """
    Subclassed CfgTableWidget to use muli-line edits for storing the custom GCODE.
    """

    def __init__(self, text, columns = None, parent = None):
        """
        Initialization of the CfgTableCustomActions class (editable 2D table for storing custom GCODE).
        @param text: text string associated with the table
        @param columns: string list containing all the columns names
        """
        CfgTable.__init__(self, text, columns, parent)

    def setCellValue(self, line, column, value):
        """
        This function is reimplemented to use QTextEdit into the table, thus allowing multi-lines custom GCODE to be stored
        @param line: line number (int)
        @param column: column number (int)
        @param value: cell content (string)
        """
        if column > 0:
            #Special case for column 1 : we use QTextEdit for storing the GCODE
            text_edit = QTextEdit()
            text_edit.setAcceptRichText(False)
            text_edit.setAutoFormatting(QTextEdit.AutoNone)
            text_edit.setPlainText(value)
            self.tablewidget.setCellWidget(line, column, text_edit)
        else:
            #Normal case: use standard QT functions
            CfgTable.setCellValue(self, line, column, value)

    def validateValue(self):
        """
        Check that the keys are unique and not empty
        @return (result_bool, result_string):
         - result_bool: True if no errors were encountered, False otherwise
         - result_string: a string containing all the errors encountered during the validation
        """
        #For now everything is OK
        result_string = ''
        result_bool = True
        keys_list = []
        
        if self.tablewidget.rowCount() > 0 and self.tablewidget.columnCount() > 0:
            for i in range(self.tablewidget.rowCount()):
                if not self.tablewidget.item(i, 0) or not self.tablewidget.item(i, 0).text():
                    result_bool = False
                    result_string += str(self.tr('\nThe cell at line {0}, column 0 must not be empty for the table "{1}"\n')).format(i, self.label.text())
                else:
                    #Create a list with all the "keys" from the first column (here a key is the custom action name)
                    keys_list.append(self.tablewidget.item(i, 0).text())
            
            nb_duplicate_elements = len(keys_list) - len(set(keys_list))
            if nb_duplicate_elements != 0:
                #There are duplicate entries, that's wrong because the key must be unique
                result_bool = False
                result_string += str(self.tr('\nFound {0} duplicate elements for the table "{1}"\n')).format(nb_duplicate_elements, self.label.text())
            
        return (result_bool, result_string)

    def getValue(self):
        """
        @return: a nested dictionnary that can be directly used to update the ConfigObj (class that handles configuration file)
        Example of returned value:
        {'pause': {'gcode': 'M5 (Spindle off)\nM9 (Coolant off)\nM0\n\nM8\nS5000M03 (Spindle 5000rpm cw)\n'}, 'probe_tool': {'gcode': '\nO<Probe_Tool> CALL\nS6000 M3 M8\n'}}
        """
        result_dict = {}
        #Get the keys (first column)
        for i in range(self.tablewidget.rowCount()):
            key = self.tablewidget.item(i, 0)
            if not key:
                continue
            key = str(key.text())
            if not key:
                continue
            result_dict[key] = {}
            
            #Get the values (other columns)
            j = 1
            while j < self.tablewidget.columnCount():
                sub_key = self.keys[j] #Column name
                value = self.tablewidget.cellWidget(i, j)
                if not value:
                    j += 1
                    continue
                value = str(value.toPlainText())
                if sub_key is not None:
                    result_dict[key][sub_key] = value
                j += 1
        
        return result_dict


class CfgTableToolParameters(CfgTable):
    """
    Subclassed CfgTableWidget to use muli-line edits for storing the custom GCODE.
    """

    def __init__(self, text, columns = None, parent = None):
        """
        Initialization of the CfgTableWidget class (editable 2D table for storing the tools table).
        @param text: text string associated with the table
        @param columns: string list containing all the columns names
        """
        self.max_tool_number = 0
        CfgTable.__init__(self, text, columns, parent)

    def setCellValue(self, line, column, value):
        """
        This function is reimplemented to use QTextEdit into the table, thus allowing multi-lines custom GCODE to be stored
        @param line: line number (int)
        @param column: column number (int)
        @param value: cell content (string or int or float)
        """
        if column > 0:
            #we use QDoubleSpinBox for storing the values
            spinbox = CorrectedDoubleSpinBox()
            spinbox.setMinimum(0)
            spinbox.setMaximum(1000000000) #Default value is 99
            computed_value = 0.0
            try: computed_value = float(value) #Convert the value to float
            except ValueError: pass
            spinbox.setValue(computed_value)
        else:
            #tool number is an integer
            spinbox = QSpinBox()
            spinbox.setMinimum(0)
            spinbox.setMaximum(1000000000) #Default value is 99
            
            computed_value = 0
            try:
                computed_value = int(value) #Convert the value to int (we may receive a string for example)
            except ValueError:
                computed_value = self.max_tool_number + 1
            self.max_tool_number = max(self.max_tool_number, computed_value) #Store the max value for the tool number, so that we can automatically increment this value for new tools
            spinbox.setValue(computed_value) #first column is the key, it must be an int
        
        self.tablewidget.setCellWidget(line, column, spinbox)

    def validateValue(self):
        """
        Check that the keys are unique and not empty
        @return (result_bool, result_string):
         - result_bool: True if no errors were encountered, False otherwise
         - result_string: a string containing all the errors encountered during the validation
        """
        #For now everything is OK
        contains_tool_1 = False
        result_string = ''
        result_bool = True
        keys_list = []
        
        if self.tablewidget.rowCount() > 0 and self.tablewidget.columnCount() > 0:
            for i in range(self.tablewidget.rowCount()):
                if not self.tablewidget.cellWidget(i, 0):
                    result_bool = False
                    result_string += str(self.tr('\nThe cell at line {0}, column 0 must not be empty for the table "{1}"\n')).format(i, self.label.text())
                else:
                    #Create a list with all the "keys" from the first column (here a key is the custom action name)
                    keys_list.append(str(self.tablewidget.cellWidget(i, 0).value()))
                    if self.tablewidget.cellWidget(i, 0).value() == 1:
                        contains_tool_1 = True
            
            nb_duplicate_elements = len(keys_list) - len(set(keys_list))
            if nb_duplicate_elements != 0:
                #There are duplicate entries, that's wrong because the key must be unique
                result_bool = False
                result_string += str(self.tr('\nFound {0} duplicate elements for the table "{1}"\n')).format(nb_duplicate_elements, self.label.text())
        
        if not contains_tool_1:
            result_bool = False
            result_string += str(self.tr('\nThe table "{0}" must always contains tool number \'1\'\n')).format(self.label.text()) #Note: str() is needed for PyQt4

        return (result_bool, result_string)

    def getValue(self):
        """
        @return: a nested dictionnary that can be directly used to update the ConfigObj (class that handles configuration file)
        Example of returned value:
        {'pause': {'gcode': 'M5 (Spindle off)\nM9 (Coolant off)\nM0\n\nM8\nS5000M03 (Spindle 5000rpm cw)\n'}, 'probe_tool': {'gcode': '\nO<Probe_Tool> CALL\nS6000 M3 M8\n'}}
        """
        result_dict = {}
        #Get the keys (first column)
        for i in range(self.tablewidget.rowCount()):
            key = self.tablewidget.cellWidget(i, 0)
            if not key:
                continue
            key = str(key.value())
            if not key:
                continue
            result_dict[key] = {}
            
            #Get the values (other columns)
            j = 1
            while j < self.tablewidget.columnCount():
                sub_key = self.keys[j] #Column name
                value = self.tablewidget.cellWidget(i, j)
                if not value:
                    j += 1
                    continue
                value = value.value()
                if sub_key is not None:
                    result_dict[key][sub_key] = value
                j += 1
        
        return result_dict
