# SPDX-License-Identifier: Apache-2.0
"""Hook PyInstaller pour `google-re2` (tiré par cel-python, donc par tout le chemin
d'import de `app.pipelines`). La roue Windows est « delvewheel » : sa `msvcp140` renommée
vit dans `google_re2.libs/`, hors de portée de l'analyse binaire de PyInstaller — sans ce
hook, le sidecar gelé échoue à l'import avec « DLL load failed while importing _re2 »."""

from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

datas, binaries = collect_delvewheel_libs_directory("re2", libdir_name="google_re2.libs")
