// Isolated runtime probe: uses generated fixtures only, no global fake keys.
#include "editor/EditorView.h"
#include <QApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMouseEvent>
#include <QPainter>
#include <QScrollBar>
#include <QTimer>
#include <dlfcn.h>
#include <cmath>
#include <functional>
#include <vector>

static muffin::EditorView *view = nullptr;
static QWidget *window = nullptr;
static std::vector<QJsonObject> results;
static std::vector<std::function<void()>> steps;
static const QRgb colors[] = {qRgb(231,76,60), qRgb(46,204,113), qRgb(52,152,219)};

static QJsonArray rectangle(QRectF r) { return {r.x(), r.y(), r.width(), r.height()}; }
static QJsonObject pixels(const QImage &image) {
    QRect boxes[3];
    int counts[3] = {};
    for (int y=0; y<image.height(); ++y)
        for (int x=0; x<image.width(); ++x) {
            const QRgb p = image.pixel(x,y) | 0xff000000;
            for (int i=0; i<3; ++i)
                if (p==colors[i]) { ++counts[i]; boxes[i] = boxes[i].united(QRect(x,y,1,1)); }
        }
    QJsonArray sizes, amounts;
    QRect all;
    for (int i=0; i<3; ++i) { sizes.append(rectangle(boxes[i])); amounts.append(counts[i]); all=all.united(boxes[i]); }
    return {{"bands",sizes},{"counts",amounts},{"all",rectangle(all)}};
}
static const muffin::BlockLayout *firstBlock() {
    for (int y=5; y<view->viewport()->height(); y+=5) {
        auto hit=view->hitTest(QPointF(view->viewport()->width()/2.,y));
        if (hit.blockId.isValid())
            if (auto *block=view->blockLayoutForNode(hit.blockId)) return block;
    }
    return nullptr;
}
static void capture(const char *name) {
    const auto *block=firstBlock();
    if (!block) { qWarning()<<"IMAGE_NO_BLOCK"<<name; qApp->exit(1); return; }
    const QRectF bounds=block->rect();
    QImage canvas(qMax(1,int(std::ceil(bounds.width()))),qMax(1,int(std::ceil(bounds.height()+4))),QImage::Format_RGB32);
    canvas.fill(Qt::white);
    {
        QPainter painter(&canvas);
        painter.translate(-bounds.topLeft());
        block->paint(painter,view->theme(),0,nullptr);
    }
    const auto *in=block->inlineLayout();
    QJsonObject row{{"stage",QString::fromLatin1(name)},{"viewport",rectangle(view->viewport()->rect())},
        {"block",rectangle(bounds)},{"block_pixels",pixels(canvas)},
        {"scroll_value",view->verticalScrollBar()->value()},{"scroll_max",view->verticalScrollBar()->maximum()},
        {"display",in ? in->displayText() : QString()},{"literal",block->literal()},
        {"visual",in ? rectangle(in->visualTextBounds()) : QJsonArray()}};
    QImage viewport=view->viewport()->grab().toImage().convertToFormat(QImage::Format_RGB32);
    row.insert("viewport_pixels",pixels(viewport));
    const QString out=qEnvironmentVariable("MUFFIN_IMAGE_PROBE_OUT");
    const auto save=[&](QImage image,const QString &suffix) {
        if (image.width()>1600 || image.height()>1600)
            image=image.scaled(1600,1600,Qt::KeepAspectRatio,Qt::SmoothTransformation);
        image.save(out+QLatin1Char('/')+QString::fromLatin1(name)+suffix+QStringLiteral(".png"));
    };
    save(canvas,QStringLiteral("-block"));
    save(viewport,QStringLiteral("-viewport"));
    qWarning().noquote()<<"IMAGE_RESULT"<<QJsonDocument(row).toJson(QJsonDocument::Compact);
    results.push_back(row);
}
static void clickImage() {
    view->setFocus();
    const QPointF p(view->viewport()->width()/2.,80);
    const QPointF global=view->viewport()->mapToGlobal(p.toPoint());
    QMouseEvent press(QEvent::MouseButtonPress,p,global,Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
    QMouseEvent release(QEvent::MouseButtonRelease,p,global,Qt::LeftButton,Qt::NoButton,Qt::NoModifier);
    QApplication::sendEvent(view->viewport(),&press);
    QApplication::sendEvent(view->viewport(),&release);
}
static void runStep(int index) {
    if (index>=int(steps.size())) {
        QJsonArray rows;
        for (const auto &r:results) rows.append(r);
        QFile out(qEnvironmentVariable("MUFFIN_IMAGE_PROBE_OUT")+QStringLiteral("/geometry.json"));
        if (out.open(QIODevice::WriteOnly)) out.write(QJsonDocument(rows).toJson());
        qApp->exit(0);
        return;
    }
    steps[index]();
    QTimer::singleShot(450,qApp,[index]{runStep(index+1);});
}
int QCoreApplication::exec() {
    using Exec=int(*)();
    auto original=reinterpret_cast<Exec>(dlsym(RTLD_NEXT,"_ZN16QCoreApplication4execEv"));
    QTimer::singleShot(1600,qApp,[]{
        for (auto *w:QApplication::allWidgets())
            if (auto *v=qobject_cast<muffin::EditorView*>(w); v && v->isVisible()) {view=v;break;}
        if (!view) {qWarning()<<"IMAGE_NO_EDITOR";qApp->exit(1);return;}
        window=view->window();
        window->resize(1050,760);
        steps={
            []{},
            []{capture("normal");window->resize(620,760);},
            []{capture("narrow");window->showMaximized();},
            []{capture("maximized");window->showFullScreen();},
            []{capture("fullscreen");window->showNormal();window->resize(1050,760);},
            []{capture("restored");view->setZoomPercent(200);},
            []{capture("zoom-200");view->setZoomPercent(80);},
            []{capture("zoom-80");view->setZoomPercent(120);},
            []{capture("zoom-restored");clickImage();},
            []{capture("image-click");}
        };
        if (qEnvironmentVariableIsSet("MUFFIN_IMAGE_SCROLL_TEST")) {
            steps.push_back([]{view->verticalScrollBar()->setValue(view->verticalScrollBar()->maximum());});
            steps.push_back([]{capture("scrolled-bottom");});
        }
        runStep(0);
    });
    return original();
}
