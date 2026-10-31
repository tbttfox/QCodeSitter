import Qt

# Qt.py <2.0 doesn't expose these for Qt4 compatibility
# When Qt.py updates to >2.0 this should be unnecessary
if Qt.IsPyQt4 or Qt.IsPySide:
    raise RuntimeError("QCodeSitter doesn't work with Qt4")
elif Qt.IsPyQt5 or Qt.IsPyQt6 or Qt.IsPySide2 or Qt.IsPySide6:
    pass
