import Qt

# Qt.py <2.0 doesn't expose these for Qt4 compatibility
# When Qt.py updates to >2.0 this should be unnecessary
if Qt.IsPyQt4 or Qt.IsPySide:
    raise RuntimeError("QCodeSitter doesn't work with Qt4")
elif Qt.IsPyQt5:
    from PyQt5.QtWidgets import QProxyStyle
    from PyQt5.QtGui import QGuiApplication
elif Qt.IsPyQt6:
    from PyQt6.QtWidgets import QProxyStyle
    from PyQt6.QtGui import QGuiApplication
elif Qt.IsPySide2:
    from PySide2.QtWidgets import QProxyStyle
    from PySide2.QtGui import QGuiApplication
elif Qt.IsPySide6:
    from PySide6.QtWidgets import QProxyStyle
    from PySide6.QtGui import QGuiApplication
