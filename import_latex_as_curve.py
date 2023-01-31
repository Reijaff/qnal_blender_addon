import bpy
import tempfile
import os
import hashlib
import re

class WM_OT_import_latex_as_curve(bpy.types.Operator):
    bl_idname = "wm.import_latex_as_curve"
    bl_label = "Import as curve"
    bl_options = {'UNDO'}

    latex_code: bpy.props.StringProperty(name="latex code",
                                         description="Input latex code", default="$e=mc^2$")

    def execute(self, context):

        with tempfile.TemporaryDirectory() as temp_dir:

            preamble = ''
            content = str(self.latex_code) 

            full_tex = "\n\n".join((
                "\\documentclass[preview]{standalone}",
                preamble,
                "\\begin{document}",
                content,
                "\\end{document}"
            )) + "\n"

            file_name = hashlib.md5(full_tex.encode("utf-8")).hexdigest()
            temp_file = temp_dir + os.sep + file_name

            with open(temp_file + ".tex", "w", encoding="utf-8") as tex_file:
                tex_file.write(full_tex)

            # latex to dvi
            latex_ret = os.system(" ".join((
                'latex',
                "-interaction=batchmode",
                "-halt-on-error",
                f"-output-directory=\"{temp_dir}\"",
                f"\"{temp_file}.tex\"",
                ">",
                os.devnull
            )))

            if latex_ret != 0:
                print("latex_ret : ", latex_ret)

                error_str = ""
                with open(temp_file + ".log", "r", encoding="utf-8") as log_file:
                    error_match_obj = re.search(
                        r"(?<=\n! ).*\n.*\n", log_file.read())
                    if error_match_obj:
                        error_str = error_match_obj.group()
                self.report({"ERROR"}, error_str)
                return {'FINISHED'}

            # dvi to svg
            dvisvg_ret = os.system(" ".join((
                "dvisvgm",
                f"\"{temp_file}.dvi\"",
                "-n",
                "-v",
                "0",
                "-o",
                f"\"{temp_file}.svg\"",
                ">",
                os.devnull
            )))
            if dvisvg_ret != 0:
                print("dvisvg_ret : ", dvisvg_ret)
                return {'FINISHED'}

            bpy.ops.object.select_all(action='DESELECT')

            objects_before_import = bpy.data.objects[:]

            bpy.ops.import_curve.svg(filepath=temp_file + '.svg')

            # Select imported objects
            imported_curve = [
                x for x in bpy.data.objects if x not in objects_before_import]
            active_obj = imported_curve[0]
            context.view_layer.objects.active = active_obj
            for x in imported_curve:
                x.data.dimensions = "3D"
                x.select_set(True)

            bpy.ops.object.editmode_toggle()
            bpy.ops.curve.select_all(action='SELECT')
            bpy.ops.transform.resize(value=(600, 600, 600))
            bpy.ops.object.editmode_toggle()

            bpy.ops.view3d.snap_selected_to_cursor(use_offset=False)

        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


def add_latex_menu_draw(self, context):
    self.layout.operator_context = "INVOKE_DEFAULT"
    self.layout.operator(
        WM_OT_import_latex_as_curve.bl_idname, text="LaTeX", icon="CON_TRANSFORM")


def register():
    bpy.utils.register_class(WM_OT_import_latex_as_curve)
    bpy.types.VIEW3D_MT_curve_add.append(add_latex_menu_draw)

def unregister():
    bpy.utils.unregister_class(WM_OT_import_latex_as_curve)
    bpy.types.VIEW3D_MT_curve_add.remove(add_latex_menu_draw)