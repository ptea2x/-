"""CleanCut: local image background remover and mask editor."""
import os
import sys
import traceback
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps, ImageDraw
from PySide6.QtCore import Qt, QPointF, QRectF, QThread, Signal, QSize
from PySide6.QtGui import QAction, QImage, QPixmap, QPainter, QColor, QPen, QBrush, QKeySequence
from PySide6.QtWidgets import (
 QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
 QFileDialog, QListWidget, QListWidgetItem, QSplitter, QSlider, QComboBox, QSpinBox,
 QProgressBar, QMessageBox, QColorDialog, QScrollArea, QFrame, QToolBar, QCheckBox
)

APP_NAME = '깔끔컷 - AI 배경 제거'
# Bundled model path takes priority. The build script downloads the model beforehand.
BUNDLE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
BUNDLED_MODELS = BUNDLE_ROOT / 'models'
if (BUNDLED_MODELS / 'u2netp.onnx').exists():
    os.environ['U2NET_HOME'] = str(BUNDLED_MODELS)
SUPPORTED = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


def image_open(path):
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert('RGBA')


def to_pixmap(img):
    image = img.convert('RGBA')
    raw = image.tobytes('raw', 'RGBA')
    qi = QImage(raw, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi.copy())


@dataclass
class Photo:
    path: str
    original: Image.Image
    mask: Image.Image
    history: list
    redo: list
    processed: bool = False


class AIWorker(QThread):
    progress = Signal(int, int, str)
    result = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, photos):
        super().__init__()
        self.photos = list(photos)

    def run(self):
        try:
            # rembg is imported in the worker so the interface opens without loading the AI.
            from rembg import remove, new_session
            session = new_session('u2netp')
        except Exception as exc:
            self.failed.emit('', f'AI 모델을 열지 못했습니다: {exc}')
            return
        for i, photo in enumerate(self.photos):
            self.progress.emit(i, len(self.photos), Path(photo.path).name)
            try:
                rgba = remove(photo.original, session=session).convert('RGBA')
                self.result.emit(photo.path, rgba.getchannel('A').copy())
            except Exception as exc:
                self.failed.emit(photo.path, str(exc))
        self.progress.emit(len(self.photos), len(self.photos), '완료')


class Canvas(QWidget):
    edited = Signal()
    started_stroke = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.photo = None
        self.scale = 1.0
        self.brush_size = 32
        self.strength = 100
        self.mode = 'erase'
        self.show_original = False
        self.bg = None
        self.last_pos = None
        self.setMouseTracking(True)
        self.setMinimumSize(400, 320)

    def set_photo(self, photo):
        self.photo = photo
        self.last_pos = None
        self.update_size()

    def update_size(self):
        if self.photo:
            self.setMinimumSize(max(400, round(self.photo.original.width * self.scale)),
                                max(320, round(self.photo.original.height * self.scale)))
            self.resize(self.minimumSize())
        self.update()

    def position(self):
        if not self.photo:
            return QPointF(0, 0)
        dw = self.photo.original.width * self.scale
        dh = self.photo.original.height * self.scale
        return QPointF((self.width() - dw) / 2, (self.height() - dh) / 2)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#e9edf4'))
        if not self.photo:
            p.setPen(QColor('#718096'))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '왼쪽에서 이미지를 추가해 주세요')
            return
        img = self.photo.original.copy()
        if not self.show_original:
            img.putalpha(self.photo.mask)
        orig = self.position()
        scaled_w = self.photo.original.width * self.scale
        scaled_h = self.photo.original.height * self.scale
        rect = QRectF(orig.x(), orig.y(), scaled_w, scaled_h)
        p.save()
        p.setClipRect(rect)
        if self.bg is None:
            sq = 12
            left, top = int(orig.x()), int(orig.y())
            p.fillRect(rect, QColor('#ffffff'))
            for y in range(top, int(orig.y() + scaled_h) + sq, sq):
                for x in range(left, int(orig.x() + scaled_w) + sq, sq):
                    if ((x - left) // sq + (y - top) // sq) % 2 == 0:
                        p.fillRect(x, y, sq, sq, QColor('#d5dbe5'))
        else:
            p.fillRect(rect, self.bg)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawPixmap(rect, to_pixmap(img), QRectF(0, 0, img.width, img.height))
        p.restore()
        p.setPen(QPen(QColor('#b3c1d2'), 1))
        p.drawRect(rect)
        if self.last_pos and not self.show_original:
            pt = QPointF(orig.x() + self.last_pos[0] * self.scale, orig.y() + self.last_pos[1] * self.scale)
            p.setPen(QPen(QColor('#2876dc'), 1.5))
            radius = self.brush_size * self.scale / 2
            p.drawEllipse(pt, radius, radius)

    def image_point(self, position):
        if not self.photo:
            return None
        o = self.position()
        x = (position.x() - o.x()) / self.scale
        y = (position.y() - o.y()) / self.scale
        if 0 <= x < self.photo.original.width and 0 <= y < self.photo.original.height:
            return (x, y)
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.show_original:
            return
        pt = self.image_point(event.position())
        if not pt or not self.photo:
            return
        self.started_stroke.emit()
        self.last_pos = pt
        self.apply_stroke(pt, pt)

    def mouseMoveEvent(self, event):
        pt = self.image_point(event.position())
        if event.buttons() & Qt.MouseButton.LeftButton and self.last_pos is not None and pt and not self.show_original:
            self.apply_stroke(self.last_pos, pt)
        self.last_pos = pt
        self.update()

    def mouseReleaseEvent(self, event):
        self.last_pos = None
        self.update()

    def apply_stroke(self, start, end):
        if not self.photo:
            return
        mask = self.photo.mask
        radius = max(1, self.brush_size / 2)
        # Paint target values on a separate grayscale overlay; blend with the
        # existing alpha at the requested brush strength.
        overlay = Image.new('L', mask.size, 0)
        draw = ImageDraw.Draw(overlay)
        width = max(1, round(self.brush_size))
        draw.line([start, end], fill=255, width=width, joint='curve')
        for x, y in (start, end):
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=255)
        base = np.asarray(mask, dtype=np.float32)
        opacity = np.asarray(overlay, dtype=np.float32) / 255.0 * (self.strength / 100.0)
        if self.mode == 'erase':
            target = base * (1 - opacity)
        else:
            # Restore uses source image pixels; it only changes mask opacity.
            target = base + (255 - base) * opacity
        self.photo.mask = Image.fromarray(np.clip(target, 0, 255).astype('uint8'), 'L')
        self.edited.emit()
        self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1370, 850)
        self.photos = {}
        self.worker = None
        self.bg_color = None
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet('''
          QMainWindow, QWidget {background: #f6f8fc; color: #243248; font-family: "Malgun Gothic"; font-size: 12px;}
          QPushButton { background: #ffffff; border: 1px solid #d6dfeb; border-radius: 8px; padding: 9px 13px; font-weight: 600; }
          QPushButton:hover {border-color: #2676df; background: #eff6ff;}
          QPushButton#primary {background: #1769dc; color: white; border-color: #1769dc;}
          QPushButton#primary:hover {background:#095ac8;}
          QListWidget, QScrollArea, QComboBox, QSpinBox {background: white; border: 1px solid #dce4ef; border-radius: 8px;}
          QListWidget::item {padding: 10px 7px;}
          QListWidget::item:selected {background: #dcecff; color: #185bb5;}
          QLabel#heading {font-size: 20px; font-weight: 800; color: #132e52;}
          QLabel#section {font-size: 13px; font-weight: 700; margin-top: 8px;}
          QProgressBar {border: 1px solid #d4dfeb; border-radius: 5px; text-align:center; background:white; height:18px;}
          QProgressBar::chunk {background:#2676df; border-radius:4px;}
        ''')
        base = QWidget()
        self.setCentralWidget(base)
        outer = QVBoxLayout(base)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel('✂  깔끔컷  |  AI 배경 제거 스튜디오')
        title.setObjectName('heading')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(QLabel('사진은 PC에서 처리 · 인터넷 없이 사용 가능(모델 포함 시)'))
        outer.addLayout(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        sidebar = QWidget()
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(300)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 8, 0)
        add = QPushButton('＋  이미지 추가')
        add.setObjectName('primary')
        add.clicked.connect(self.add_files)
        sl.addWidget(add)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.select_photo)
        sl.addWidget(self.list, 1)
        allbtn = QPushButton('✨ 선택한 사진 AI 제거')
        allbtn.clicked.connect(self.process_current)
        sl.addWidget(allbtn)
        batchbtn = QPushButton('✨ 모든 사진 AI 일괄 제거')
        batchbtn.clicked.connect(self.process_all)
        sl.addWidget(batchbtn)
        delbtn = QPushButton('목록에서 선택 제거')
        delbtn.clicked.connect(self.remove_current)
        sl.addWidget(delbtn)
        splitter.addWidget(sidebar)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 8, 0)
        tools = QHBoxLayout()
        self.erase_btn = QPushButton('◯ 지우개')
        self.restore_btn = QPushButton('↶ 복원 브러시')
        self.erase_btn.clicked.connect(lambda: self.set_mode('erase'))
        self.restore_btn.clicked.connect(lambda: self.set_mode('restore'))
        tools.addWidget(self.erase_btn)
        tools.addWidget(self.restore_btn)
        undo = QPushButton('↶ 실행 취소')
        undo.clicked.connect(self.undo)
        tools.addWidget(undo)
        redo = QPushButton('↷ 다시 실행')
        redo.clicked.connect(self.redo)
        tools.addWidget(redo)
        tools.addStretch()
        self.compare = QCheckBox('원본 보기 (누른 동안이 아닌 토글)')
        self.compare.toggled.connect(self.compare_original)
        tools.addWidget(self.compare)
        cl.addLayout(tools)
        self.canvas = Canvas()
        self.canvas.started_stroke.connect(self.snapshot)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.canvas)
        cl.addWidget(self.scroll, 1)
        zoomline = QHBoxLayout()
        zoomline.addWidget(QLabel('확대'))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(10, 800)
        self.zoom.setValue(100)
        self.zoom.valueChanged.connect(self.change_zoom)
        zoomline.addWidget(self.zoom, 1)
        self.zoom_label = QLabel('100%')
        zoomline.addWidget(self.zoom_label)
        cl.addLayout(zoomline)
        splitter.addWidget(center)

        panel = QWidget()
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(320)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(6, 0, 0, 0)
        pl.addWidget(self.section('브러시 크기'))
        self.brush = QSlider(Qt.Orientation.Horizontal)
        self.brush.setRange(1, 200)
        self.brush.setValue(32)
        self.brush.valueChanged.connect(lambda v: setattr(self.canvas, 'brush_size', v))
        pl.addWidget(self.brush)
        pl.addWidget(self.section('브러시 강도'))
        self.strength = QSlider(Qt.Orientation.Horizontal)
        self.strength.setRange(1, 100)
        self.strength.setValue(100)
        self.strength.valueChanged.connect(lambda v: setattr(self.canvas, 'strength', v))
        pl.addWidget(self.strength)
        pl.addWidget(self.section('배경색'))
        self.bg_combo = QComboBox()
        self.bg_combo.addItems(['투명', '흰색', '파란색', '검정', '사용자 지정'])
        self.bg_combo.currentIndexChanged.connect(self.change_bg)
        pl.addWidget(self.bg_combo)
        pl.addWidget(self.section('저장 비율'))
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems(['원본 그대로', '1:1 정사각형', '4:5 인스타', '16:9 가로', '9:16 세로', 'A4 세로'])
        pl.addWidget(self.ratio_combo)
        pl.addWidget(self.section('출력 너비 (px)'))
        self.width_box = QSpinBox()
        self.width_box.setRange(0, 12000)
        self.width_box.setSpecialValueText('원본 크기')
        self.width_box.setSingleStep(100)
        self.width_box.setValue(0)
        pl.addWidget(self.width_box)
        pl.addWidget(QLabel('비율에 맞춰 여백을 추가합니다.\n원본 사진은 잘리지 않습니다.'))
        pl.addStretch()
        save_btn = QPushButton('↓ 현재 사진 저장')
        save_btn.setObjectName('primary')
        save_btn.clicked.connect(self.save_current)
        pl.addWidget(save_btn)
        save_all = QPushButton('↓ 모두 폴더에 저장')
        save_all.clicked.connect(self.save_all)
        pl.addWidget(save_all)
        splitter.addWidget(panel)
        splitter.setSizes([255, 815, 275])
        self.progress = QProgressBar()
        self.progress.hide()
        outer.addWidget(self.progress)
        self.statusBar().showMessage('이미지를 추가하고 AI 제거 버튼을 눌러 주세요.')
        self.undo_action = QAction('실행 취소', self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.addAction(self.undo_action)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction('다시 실행', self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.addAction(self.redo_action)
        self.redo_action.triggered.connect(self.redo)
        self.set_mode('erase')

    def section(self, name):
        label = QLabel(name)
        label.setObjectName('section')
        return label

    def set_mode(self, mode):
        self.canvas.mode = mode
        self.erase_btn.setStyleSheet('background:#dcecff' if mode == 'erase' else '')
        self.restore_btn.setStyleSheet('background:#dcecff' if mode == 'restore' else '')

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '사진 추가', '', '이미지 (*.png *.jpg *.jpeg *.webp *.bmp)')
        for path in paths:
            if path in self.photos:
                continue
            try:
                img = image_open(path)
                photo = Photo(path, img, img.getchannel('A').copy(), [], [])
                self.photos[path] = photo
                item = QListWidgetItem(Path(path).name)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self.list.addItem(item)
            except Exception as exc:
                QMessageBox.warning(self, '이미지 오류', f'{path}\n{exc}')
        if self.list.count() and not self.list.currentItem():
            self.list.setCurrentRow(0)

    def current(self):
        item = self.list.currentItem()
        return self.photos.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def select_photo(self, current, previous):
        self.canvas.set_photo(self.current())
        self.compare.setChecked(False)

    def remove_current(self):
        item = self.list.currentItem()
        if item:
            self.photos.pop(item.data(Qt.ItemDataRole.UserRole), None)
            self.list.takeItem(self.list.row(item))
            self.canvas.set_photo(self.current())

    def process_current(self):
        photo = self.current()
        if photo:
            self.run_ai([photo])

    def process_all(self):
        if self.photos:
            self.run_ai(self.photos.values())

    def run_ai(self, photos):
        if self.worker and self.worker.isRunning():
            return
        self.worker = AIWorker(photos)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.ai_finished)
        self.worker.failed.connect(self.ai_failed)
        self.progress.show()
        self.worker.start()

    def update_progress(self, done, total, name):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        self.statusBar().showMessage(f'AI 처리: {done}/{total} · {name}')
        if done == total:
            self.progress.hide()

    def ai_finished(self, path, mask):
        photo = self.photos.get(path)
        if not photo:
            return
        self.push_history(photo)
        photo.mask = mask
        photo.processed = True
        if self.current() is photo:
            self.canvas.update()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                item.setText('✓  ' + Path(path).name)

    def ai_failed(self, path, message):
        QMessageBox.warning(self, 'AI 처리 오류', f'{Path(path).name}\n{message}\n\n모델이 포함되지 않았다면 인터넷 연결 후 재시도하세요.')

    def push_history(self, photo):
        photo.history.append(photo.mask.copy())
        if len(photo.history) > 12:
            photo.history.pop(0)
        photo.redo.clear()

    def snapshot(self):
        photo = self.current()
        if photo:
            self.push_history(photo)

    def undo(self):
        photo = self.current()
        if photo and photo.history:
            photo.redo.append(photo.mask.copy())
            photo.mask = photo.history.pop()
            self.canvas.update()

    def redo(self):
        photo = self.current()
        if photo and photo.redo:
            photo.history.append(photo.mask.copy())
            photo.mask = photo.redo.pop()
            self.canvas.update()

    def compare_original(self, yes):
        self.canvas.show_original = yes
        self.canvas.update()

    def change_zoom(self, value):
        self.canvas.scale = value / 100.0
        self.zoom_label.setText(f'{value}%')
        self.canvas.update_size()

    def change_bg(self, index):
        colors = [None, QColor('#ffffff'), QColor('#1769dc'), QColor('#101827')]
        if index == 4:
            color = QColorDialog.getColor(self.bg_color or QColor('#e5e7eb'), self, '배경색 선택')
            if color.isValid():
                self.bg_color = color
            else:
                self.bg_combo.setCurrentIndex(0)
                return
        else:
            self.bg_color = colors[index]
        self.canvas.bg = self.bg_color
        self.canvas.update()

    def render_output(self, photo):
        image = photo.original.copy()
        image.putalpha(photo.mask)
        ratio = [None, 1., 4/5, 16/9, 9/16, 210/297][self.ratio_combo.currentIndex()]
        if ratio is not None:
            w, h = image.size
            if w / h > ratio:
                target_w, target_h = w, int(np.ceil(w / ratio))
            else:
                target_w, target_h = int(np.ceil(h * ratio)), h
            background = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
            background.alpha_composite(image, ((target_w - w) // 2, (target_h - h) // 2))
            image = background
        width = self.width_box.value()
        if width:
            height = max(1, round(image.height * width / image.width))
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        if self.bg_color:
            color = self.bg_color
            filled = Image.new('RGBA', image.size, (color.red(), color.green(), color.blue(), 255))
            filled.alpha_composite(image)
            image = filled
        return image

    def save_current(self):
        photo = self.current()
        if not photo:
            return
        name = Path(photo.path).stem + '_clean.png'
        target, _ = QFileDialog.getSaveFileName(self, '이미지 저장', str(Path(photo.path).with_name(name)), 'PNG (*.png);;JPG (*.jpg)')
        if target:
            self.save_photo(photo, target)

    def save_photo(self, photo, target):
        try:
            image = self.render_output(photo)
            if Path(target).suffix.lower() in ('.jpg', '.jpeg'):
                if self.bg_color is None:
                    bg = Image.new('RGBA', image.size, 'white')
                    bg.alpha_composite(image)
                    image = bg
                image.convert('RGB').save(target, quality=95)
            else:
                image.save(target, 'PNG')
            self.statusBar().showMessage('저장 완료: ' + target)
        except Exception as exc:
            QMessageBox.critical(self, '저장 오류', str(exc))

    def save_all(self):
        if not self.photos:
            return
        directory = QFileDialog.getExistingDirectory(self, '저장할 폴더 선택')
        if not directory:
            return
        success = 0
        for index, photo in enumerate(self.photos.values(), start=1):
            base = Path(photo.path).stem
            dest = Path(directory) / f'{base}_clean.png'
            if dest.exists():
                dest = Path(directory) / f'{base}_clean_{index}.png'
            try:
                self.render_output(photo).save(dest, 'PNG')
                success += 1
            except Exception as exc:
                QMessageBox.warning(self, '저장 실패', f'{base}: {exc}')
        QMessageBox.information(self, '일괄 저장 완료', f'{success}장 저장했습니다.\n{directory}')


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
