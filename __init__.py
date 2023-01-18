from .pipeclient import PipeClient
from . import async_loop
from . import combine_edits
from . import add_scene_with_sound
from . import io_import_image_highlight
from . import import_latex_as_curve 
import subprocess
import requests
import hashlib
import asyncio
import shutil
import time
import aud
import sys
import os
import bpy

bl_info = {
    "name": "qnal_addon",
    "author": "reijaff",
    "description": "",
    "blender": (2, 80, 0),
    "version": (0, 3, 0),
    "location": "",
    "warning": "",
    "category": "Generic"
}


docker_client = None
docker_container = None

pipe_client = None


class QnalAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    tts_audio_project_folder: bpy.props.StringProperty(
        name="Folder name for TTS audio",
        description="Folder name for TTS audio in a specific folder alongside blend file",
        default="tts_audio",
    )

    tts_audio_preview_folder: bpy.props.StringProperty(
        name="Common folder path for TTS audio",
        description="Common folder path where TTS audio are stored",
        subtype="DIR_PATH",
        default=os.path.join(
            bpy.utils.user_resource("DATAFILES"), "tts_audio"),
    )

    docker_access: bpy.props.BoolProperty()
    audacity_initialized: bpy.props.BoolProperty()
    deps_installed: bpy.props.BoolProperty()

    docker_server_status: bpy.props.StringProperty(
        name="docker server status", description="docker server status", default="off"
    )

    tts_server_status: bpy.props.StringProperty(
        name="tts server status", description="tts server status", default="free"
    )

    def draw(self, context):
        # logger.info(f"Draw addon preferences {self.docker_access}")
        box = self.layout.box()

        row = box.row(align=True)
        row.operator("qnal.deps_check",
                     text="Check dependencies", icon="QUESTION")
        if self.deps_installed:
            row.label(text="Dependencies are installed", icon="CHECKBOX_HLT")
        else:
            row.operator(
                "qnal.deps_install", text="Install dependencies", icon="CHECKBOX_DEHLT"
            )

        if self.docker_access:
            box.operator(
                "qnal.docker_check", text="Docker access ensured", icon="CHECKBOX_HLT"
            )
        else:
            box.operator(
                "qnal.docker_check",
                text="Ensure your docker access",
                icon="CHECKBOX_DEHLT",
            )

        if self.audacity_initialized:
            box.operator(
                "qnal.audacity_check", text="Audacity API ensured", icon="CHECKBOX_HLT"
            )
        else:
            box.operator(
                "qnal.audacity_check",
                text="Ensure Audacity Python API",
                icon="CHECKBOX_DEHLT",
            )


def init_deps_check():
    addon_prefs = bpy.context.preferences.addons[__package__].preferences
    # logger.info("Checking dependencies")

    try:
        import pip
        import docker

        # logger.info(f"pip filepath : {pip.__file__}")

        addon_prefs.deps_installed = True
    except:
        addon_prefs.deps_installed = False


class Deps_Check(bpy.types.Operator):

    bl_label = "Check dependencies"
    bl_idname = "qnal.deps_check"

    bl_description = "Check dependencies"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        init_deps_check()
        return {"FINISHED"}

    def register():
        init_deps_check()


class Deps_Install(bpy.types.Operator):

    bl_label = "Install Dependencies"
    bl_idname = "qnal.deps_install"
    bl_description = "Install dependencies"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # logger.info("Installing dependencies")
        # logger.info(f"python path : {sys.executable}")

        binary_path = bpy.app.binary_path
        blender_dir_path = os.path.dirname(binary_path)
        version_dir = ".".join(map(str, bpy.app.version[0:2]))
        target = os.path.join(
            blender_dir_path,
            version_dir,
            os.path.relpath("python/lib"),
            os.path.basename(sys.executable),
            os.path.relpath("site-packages"),
        )

        packages = ["docker"]

        _ret = subprocess.check_call([sys.executable, "-m", "ensurepip"])
        # logger.info(f"--> ensurepip : {_ret}")

        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                f"--target={target}",
                "--upgrade",
                "pip",
            ]
        )

        for package in packages:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install",
                    f"--target={target}", package]
            )

        init_deps_check()

        return {"FINISHED"}


def init_docker():
    global docker_client
    # logger.info("Init Docker")

    addon_prefs = bpy.context.preferences.addons[__package__].preferences
    try:
        if docker_client == None:
            import docker
            docker_client = docker.from_env()

        addon_prefs.docker_access = docker_client.ping()  # TODO
    except:
        addon_prefs.docker_access = False  # TODO


class Docker_Check(bpy.types.Operator):

    bl_label = "Check docker"
    bl_idname = "qnal.docker_check"
    bl_description = "Check your docker access"
    bl_options = {"REGISTER", "UNDO"}

    # client = freesound_api.FreesoundClient()

    def execute(self, context):
        init_docker()
        return {"FINISHED"}

    def register():
        init_docker()


class Docker_Launch(bpy.types.Operator, async_loop.AsyncModalOperatorMixin):

    bl_label = "Launch docker"
    bl_idname = "qnal.docker_launch"
    bl_description = "Launch docker tts server"
    bl_options = {"REGISTER", "UNDO"}

    # client = freesound_api.FreesoundClient()

    async def async_execute(self, context):
        global docker_client
        global docker_container
        addon_prefs = bpy.context.preferences.addons[__package__].preferences

        if docker_client == None:
            import docker

            docker_client = docker.from_env()

        docker_container = docker_client.containers.run(
            "ghcr.io/coqui-ai/tts-cpu:latest",
            "--model_name tts_models/en/vctk/vits",
            entrypoint="tts-server",
            detach=True,
            volumes={
                f"/home/{os.getlogin()}/.local/share/tts": {
                    "bind": "/root/.local/share/tts",
                    "mode": "rw",
                }
            },
            ports={"5002/tcp": ("127.0.0.1", 5002)},
        )

        # logger.info("before request")
        addon_prefs.docker_server_status = "loading ..."
        while True:
            await asyncio.sleep(1)
            try:
                response = requests.get("http://127.0.0.1:5002/")
                if response.status_code == 200:
                    break
            except:
                pass

        addon_prefs.docker_server_status = "on"

        self.quit()
        # return {'FINISHED'}


def docker_stop():
    global docker_client
    global docker_container
    addon_prefs = bpy.context.preferences.addons[__package__].preferences

    if docker_container == None:
        addon_prefs.docker_server_status = "off"
    else:
        docker_container.stop()
        docker_container = None
        addon_prefs.docker_server_status = "off"


class Docker_Stop(bpy.types.Operator):

    bl_label = "Stop docker"
    bl_idname = "qnal.docker_stop"
    bl_description = "Stop docker tts server"
    bl_options = {"REGISTER", "UNDO"}

    # client = freesound_api.FreesoundClient()

    def execute(self, context):
        docker_stop()
        return {"FINISHED"}

    def unregister():
        bpy.context.preferences.addons[
            __package__
        ].preferences.docker_server_status = "off"
        docker_stop()


def doCommand(cmd):
    global pipe_client
    reply = ""
    pipe_client.write(cmd)
    start_time = time.time()
    while reply == "":
        time.sleep(0.1)
        if time.time() - start_time > 1 and cmd != "De-Clicker":
            reply = "Timeout"
            print(reply)
            sys.exit()

        reply = pipe_client.read()

    print(reply)
    return reply


def init_audacity():
    global pipe_client
    # logger.info("Init Audacity")
    addon_prefs = bpy.context.preferences.addons[__package__].preferences

    try:
        if pipe_client == None:
            pipe_client = PipeClient()

        reply = doCommand("Help")

        addon_prefs.audacity_initialized = True
    except:
        addon_prefs.audacity_initialized = False

    # logger.info(f"--> audacity_initialized : {addon_prefs.audacity_initialized}")


class Audacity_Check(bpy.types.Operator):

    bl_label = "Check Audacity Python API"
    bl_idname = "qnal.audacity_check"
    bl_description = "Check your Audacity Python API"
    bl_options = {"REGISTER", "UNDO"}

    # client = freesound_api.FreesoundClient()

    def execute(self, context):
        init_audacity()
        return {"FINISHED"}

    def register():
        init_audacity()


class QnalData(bpy.types.PropertyGroup):
    """Setting per Scene"""

    preview_location: bpy.props.EnumProperty(
        items=[
            (
                "PROJECT",
                "Project Directory",
                "Preview will be stored in the project directory",
            ),
            (
                "COMMON",
                "Common Directory",
                "Preview will be stored in a common directory specified in preferences",
            ),
        ],
        name="Preview Location",
        default="COMMON",
        description="Where to store tts preview sound files",
    )

    download_location: bpy.props.EnumProperty(
        items=[
            (
                "PROJECT",
                "Project Directory",
                "Preview will be stored in the Project Directory",
            ),
            (
                "COMMON",
                "Common Directory",
                "Preview will be stored in a common directory specified in preferences",
            ),
        ],
        name="Download Location",
        default="PROJECT",
        description="Where to store tts sound files",
    )

    model_name: bpy.props.EnumProperty(
        items=[
            ("tts_models/en/vctk/vits",) * 3,
        ],
        name="TTS Model Name",
        default="tts_models/en/vctk/vits",
        description="Choose TTS Model Name",
    )

    vctk_vits_speaker_idx: bpy.props.EnumProperty(
        items=[
            ("p225",) * 3,
            ("p226",) * 3,
            ("p227",) * 3,
            ("p228",) * 3,
            ("p229",) * 3,
            ("p230",) * 3,
            ("p231",) * 3,
            ("p232",) * 3,
            ("p233",) * 3,
            ("p234",) * 3,
            ("p236",) * 3,
            ("p237",) * 3,
            ("p238",) * 3,
            ("p239",) * 3,
            ("p240",) * 3,
            ("p241",) * 3,
            ("p243",) * 3,
            ("p244",) * 3,
            ("p245",) * 3,
            ("p246",) * 3,
            ("p247",) * 3,
            ("p248",) * 3,
            ("p249",) * 3,
            ("p250",) * 3,
            ("p251",) * 3,
            ("p252",) * 3,
            ("p253",) * 3,
            ("p254",) * 3,
            ("p255",) * 3,
            ("p256",) * 3,
            ("p257",) * 3,
            ("p258",) * 3,
            ("p259",) * 3,
            ("p260",) * 3,
            ("p261",) * 3,
            ("p262",) * 3,
            ("p263",) * 3,
            ("p264",) * 3,
            ("p265",) * 3,
            ("p266",) * 3,
            ("p267",) * 3,
            ("p268",) * 3,
            ("p269",) * 3,
            ("p270",) * 3,
            ("p271",) * 3,
            ("p272",) * 3,
            ("p273",) * 3,
            ("p274",) * 3,
            ("p275",) * 3,
            ("p276",) * 3,
            ("p277",) * 3,
            ("p278",) * 3,
            ("p279",) * 3,
            ("p280",) * 3,
            ("p281",) * 3,
            ("p282",) * 3,
            ("p283",) * 3,
            ("p284",) * 3,
            ("p285",) * 3,
            ("p286",) * 3,
            ("p287",) * 3,
            ("p288",) * 3,
            ("p292",) * 3,
            ("p293",) * 3,
            ("p294",) * 3,
            ("p295",) * 3,
            ("p297",) * 3,
            ("p298",) * 3,
            ("p299",) * 3,
            ("p300",) * 3,
            ("p301",) * 3,
            ("p302",) * 3,
            ("p303",) * 3,
            ("p304",) * 3,
            ("p305",) * 3,
            ("p306",) * 3,
            ("p307",) * 3,
            ("p308",) * 3,
            ("p310",) * 3,
            ("p311",) * 3,
            ("p312",) * 3,
            ("p313",) * 3,
            ("p314",) * 3,
            ("p316",) * 3,
            ("p317",) * 3,
            ("p318",) * 3,
            ("p323",) * 3,
            ("p326",) * 3,
            ("p329",) * 3,
            ("p330",) * 3,
            ("p333",) * 3,
            ("p334",) * 3,
            ("p335",) * 3,
            ("p336",) * 3,
            ("p339",) * 3,
            ("p340",) * 3,
            ("p341",) * 3,
            ("p343",) * 3,
            ("p345",) * 3,
            ("p347",) * 3,
            ("p351",) * 3,
            ("p360",) * 3,
            ("p361",) * 3,
            ("p362",) * 3,
            ("p363",) * 3,
            ("p364",) * 3,
            ("p374",) * 3,
            ("p376",) * 3,
        ],
        name="Vctk Vits speakers",
        default="p270",
        description="Choose TTS speaker id",
    )

    audio_is_playing: bpy.props.BoolProperty(description="Audio is playing")

    audacity_declicker: bpy.props.BoolProperty(
        description="Apply Audacity De-Clicker on audio", default=False
    )

    input_text: bpy.props.StringProperty(
        description="Text to synthesize", default="Everything is a test!"
    )


def tts_output(audio_filepath):
    global pipe_client
    addon_prefs = bpy.context.preferences.addons[__package__].preferences
    addon_data = bpy.context.scene.qnal_data

    addon_prefs.tts_server_status = "processing"
    payload = {
        "text": addon_data.input_text,
        "speaker_id": addon_data.vctk_vits_speaker_idx,
    }
    ret = requests.get("http://127.0.0.1:5002/api/tts", params=payload)
    addon_prefs.tts_server_status = "free"

    with open(audio_filepath, "wb") as f:
        f.write(ret.content)

    if addon_data.audacity_declicker:
        if pipe_client == None:
            pipe_client = PipeClient()

        # doCommand( 'SetProject: X=10 Y=10 Width=910 Height=800' )
        doCommand("SelectAll")
        doCommand("RemoveTracks")
        doCommand(f"Import2: Filename={audio_filepath}")
        doCommand("Select: Track=0")
        doCommand("SelTrackStartToEnd")
        doCommand("De-Clicker")
        doCommand('TruncateSilence: Action="Compress Excess Silence" Compress=10')
        doCommand("LoudnessNormalization")
        doCommand("Select: Start=0 End=0.1")
        doCommand("FadeIn")

        # add filename + path
        doCommand("SelTrackStartToEnd")
        doCommand(f"Export2: Filename={audio_filepath}")

        doCommand("SelectAll")
        doCommand("RemoveTracks")


class TTS_Audio_Add(bpy.types.Operator):
    bl_label = "Add"
    bl_idname = "qnal.tts_audio_add"
    bl_description = "Add sound to the VSE at the current frame"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon_prefs = bpy.context.preferences.addons[__package__].preferences

        _input_text = bpy.context.scene.qnal_data.input_text
        _preview_folder = addon_prefs.tts_audio_preview_folder

        if _input_text == "":
            return {"FINISHED"}

        if not bpy.data.is_saved:
            return {"FINISHED"}

        # algorithm for audio name
        audio_name = hashlib.md5(
            _input_text.encode("utf-8")).hexdigest() + ".wav"

        # create directory for audio
        folderpath = os.path.join(
            os.path.dirname(
                bpy.data.filepath), addon_prefs.tts_audio_project_folder
        )
        if not os.path.isdir(folderpath):
            os.makedirs(folderpath, exist_ok=True)
        audio_filepath = os.path.join(folderpath, audio_name)

        preview_filepath = os.path.join(_preview_folder, audio_name)

        if os.path.isfile(preview_filepath):
            shutil.copy(preview_filepath, audio_filepath)

        if not os.path.isfile(audio_filepath):
            tts_output(audio_filepath)

        if not bpy.context.scene.sequence_editor:
            bpy.context.scene.sequence_editor_create()

        if not bpy.context.sequences:
            addSceneChannel = 1
        else:
            channels = [s.channel for s in bpy.context.sequences]
            channels = sorted(list(set(channels)))
            empty_channel = channels[-1] + 1
            addSceneChannel = empty_channel

        newStrip = bpy.context.scene.sequence_editor.sequences.new_sound(
            name=os.path.basename(audio_filepath),
            filepath=f"//{addon_prefs.tts_audio_project_folder}/{audio_name}",
            channel=addSceneChannel,
            frame_start=bpy.context.scene.frame_current,
        )
        newStrip.show_waveform = True
        newStrip.sound.use_mono = True
        # bpy.context.scene.sequence_editor.sequences_all[
        # newStrip.name
        # ].frame_start = bpy.context.scene.frame_current

        return {"FINISHED"}


class TTS_Audio_Play(bpy.types.Operator):
    bl_label = "Play"
    bl_idname = "qnal.tts_audio_play"
    bl_description = "Play audio preview"
    bl_options = {"REGISTER", "UNDO"}
    handle = 0

    def execute(self, context):
        addon_prefs = bpy.context.preferences.addons[__package__].preferences
        addon_data = bpy.context.scene.qnal_data
        _preview_folder = addon_prefs.tts_audio_preview_folder
        _input_text = bpy.context.scene.qnal_data.input_text

        if _input_text == "":
            return {"FINISHED"}

        if not bpy.data.is_saved:
            return {"FINISHED"}

        # algorithm for audio name
        audio_name = hashlib.md5(
            _input_text.encode("utf-8")).hexdigest() + ".wav"

        # create directory for audio

        if not os.path.isdir(_preview_folder):
            os.makedirs(_preview_folder, exist_ok=True)
        audio_filepath = os.path.join(_preview_folder, audio_name)

        if not os.path.isfile(audio_filepath):
            tts_output(audio_filepath)

        try:

            # Playing file audio_filepath
            addon_data.audio_is_playing = True
            device = aud.Device()
            audio = aud.Sound.file(audio_filepath)

            TTS_Audio_Play.handle = device.play(audio)
            TTS_Audio_Play.handle.loop_count = -1  # TODO

        except Exception as e:
            self.report({"WARNING"}, f"[Play] Error ... {e}")
            return {"CANCELLED"}

        return {"FINISHED"}


class TTS_Audio_Pause(bpy.types.Operator):
    bl_label = "Pause"
    bl_idname = "qnal.tts_audio_pause"
    bl_description = "Pause audio preview"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon_data = context.scene.qnal_data
        # if (addon_data.audio_loaded):
        addon_data.audio_is_playing = False
        TTS_Audio_Play.handle.stop()
        return {"FINISHED"}


class TTS_PT_Panel(bpy.types.Panel):
    bl_label = "Text To Speach"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "TTS"

    @classmethod
    def poll(self, context):
        return context.space_data.view_type in {"SEQUENCER", "SEQUENCER_PREVIEW"}

    def draw(self, context):
        addon_prefs = bpy.context.preferences.addons[__package__].preferences

        # self.logger.info(f"docker access:{addon_prefs.docker_access}")
        if not addon_prefs.docker_access:
            col = self.layout.column(align=True)
            col.label(text="Error accessing docker", icon="ERROR")
            col.label(text="Check Addon Preferences")


class TTS_PT_subpanel_synthesize(bpy.types.Panel):
    bl_parent_id = "TTS_PT_Panel"
    bl_label = "Synthesize"

    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "TTS"

    @classmethod
    def poll(cls, context):
        return bpy.context.preferences.addons[__package__].preferences.docker_access

    def draw(self, context):
        addon_prefs = bpy.context.preferences.addons[__package__].preferences
        addon_data = context.scene.qnal_data
        if addon_prefs.docker_server_status != "on":
            col = self.layout.column(align=True)
            col.label(text="Error accessing docker server", icon="ERROR")
            col.label(text="Launch docker server first")
        else:

            col = self.layout.column(align=True)
            # col.scale_y = 2
            col.prop(addon_data, "input_text", text="", icon="RIGHTARROW")

            row = self.layout.row(align=True)
            if addon_data.audio_is_playing:
                row.operator("qnal.tts_audio_pause",
                             text="Pause", icon="PAUSE")
            else:
                row.operator("qnal.tts_audio_play",
                             text="Play", icon="PLAY_SOUND")

            # row.separator()
            row.operator("qnal.tts_audio_add",
                         text="Add", icon="NLA_PUSHDOWN")


class TTS_PT_subpanel_settings(bpy.types.Panel):
    bl_parent_id = "TTS_PT_Panel"
    bl_label = "Scene Settings"

    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"
    bl_category = "TTS"

    def draw(self, context):
        addon_data = context.scene.qnal_data
        addon_prefs = bpy.context.preferences.addons[__package__].preferences

        col = self.layout.column(align=True)
        # col.operator("qnal.test_operator", text="test operator")
        if addon_prefs.audacity_initialized:
            col.prop(
                addon_data,
                "audacity_declicker",
                text="Audacity De-Clicker",
                toggle=True,
            )
        else:
            col.label(text="Error accessing Audacity", icon="ERROR")
            col.label(text="Setup Audacity Python API")

        box = self.layout.box()
        col = box.column()  # align=True)
        col.label(text="TTS server settings")

        row = col.row(align=True)
        row.label(text="Docker server status:")
        row.label(text=addon_prefs.docker_server_status)

        col.prop(addon_data, "model_name", text="Model")
        col.prop(addon_data, "vctk_vits_speaker_idx", text="Speaker id")

        if addon_prefs.docker_server_status == "on":
            col.operator("qnal.docker_stop",
                         text="Stop docker server", icon="PAUSE")
        elif addon_prefs.docker_server_status == "loading ...":
            col.label(text=addon_prefs.docker_server_status)
        elif addon_prefs.docker_server_status == "off":
            col.operator("qnal.docker_launch",
                         text="Launch docker server", icon="PLAY")


class Test_Operator(bpy.types.Operator):

    bl_label = "Test operator"
    bl_idname = "qnal.test_operator"
    bl_description = "test operator"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # bpy.ops.render.render(animation=True, seq)
        print("start")
        _start = time.time()
        # bpy.ops.render.opengl(animation=True, sequencer=True)
        # bpy.ops.render.render(animation=True, use_viewport=True)
        doCommand('Help')
        print("end", time.time() - _start)

        return {"FINISHED"}


# order matters
classes = (
    QnalAddonPreferences,
    async_loop.AsyncLoopModalOperator,
    QnalData,
    Deps_Check,
    Deps_Install,
    Audacity_Check,
    Docker_Check,
    Docker_Launch,
    Docker_Stop,
    TTS_Audio_Play,
    TTS_Audio_Add,
    TTS_Audio_Pause,
    TTS_PT_Panel,
    TTS_PT_subpanel_synthesize,
    TTS_PT_subpanel_settings,

    # Test_Operator,

    combine_edits.Qnal_Combine_Edits,
    add_scene_with_sound.Qnal_Add_Scene_With_Sound,
    add_scene_with_sound.SEQUENCER_MT_add_scene_and_sound,
    io_import_image_highlight.IMPORT_IMAGE_OT_to_plane_highlight,
    import_latex_as_curve.WM_OT_import_latex_as_curve
)


def register():
    async_loop.setup_asyncio_executor()

    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.qnal_data = bpy.props.PointerProperty(
        type=QnalData)

    bpy.types.VIEW3D_MT_add.append(import_latex_as_curve.add_latex_menu_draw)

    bpy.types.SEQUENCER_MT_add.append(combine_edits.combine_edits_menu_draw)
    bpy.types.SEQUENCER_MT_add.append(
        add_scene_with_sound.add_scene_and_sound_menu_draw)

    bpy.types.TOPBAR_MT_file_import.append(
        io_import_image_highlight.import_images_highlight_button)
    bpy.types.VIEW3D_MT_image_add.append(
        io_import_image_highlight.import_images_highlight_button)

    bpy.app.handlers.load_post.append(
        io_import_image_highlight.register_driver)
    io_import_image_highlight.register_driver()


def unregister():
    global pipe_client
    if pipe_client is not None and pipe_client._write_pipe is not None:
        pipe_client.close()

    for c in classes[::-1]:
        bpy.utils.unregister_class(c)

    bpy.types.VIEW3D_MT_add.remove(import_latex_as_curve.add_latex_menu_draw)

    bpy.types.SEQUENCER_MT_add.remove(combine_edits.combine_edits_menu_draw)
    bpy.types.SEQUENCER_MT_add.remove(
        add_scene_with_sound.add_scene_and_sound_menu_draw)

    bpy.types.TOPBAR_MT_file_import.remove(
        io_import_image_highlight.import_images_highlight_button)
    bpy.types.VIEW3D_MT_image_add.remove(
        io_import_image_highlight.import_images_highlight_button)

    if io_import_image_highlight.check_drivers in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(
            io_import_image_highlight.check_drivers)

    bpy.app.handlers.load_post.remove(
        io_import_image_highlight.register_driver)
    # del bpy.app.driver_namespace['import_image__find_plane_corner']
