// Isolated integration driver; deliberately never calls QInputMethod::update.
#include <QAbstractScrollArea>
#include <QAction>
#include <QApplication>
#include <QDebug>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPointer>
#include <QScrollBar>
#include <QTimer>
#include <QWindow>
#include <dlfcn.h>
#include <functional>
#include <vector>

static QWidget *editor = nullptr;
static QWidget *window = nullptr;
static QRectF sentRect;
static QPointer<QWindow> sentWindow;
static int notifications = 0;
static int previousNotifications = 0;
static int failures = 0;
static std::vector<std::function<void()>> steps;

static QWidget *findEditor(const char *name) {
    for (auto *candidate : QApplication::allWidgets())
        if (QByteArray(candidate->metaObject()->className()) == name && candidate->isVisible())
            return candidate;
    return nullptr;
}
static QRectF currentGlobalRect() {
    auto *w = QGuiApplication::focusWindow();
    return w ? QGuiApplication::inputMethod()->cursorRectangle().translated(w->mapToGlobal(QPoint())) : QRectF();
}
static void check(const char *name, bool needsNew = true) {
    const QRectF expected = currentGlobalRect();
    const bool ok = expected.isValid() && sentWindow == QGuiApplication::focusWindow() && expected == sentRect &&
        (!needsNew || notifications > previousNotifications);
    qWarning().nospace() << "ACCEPT " << name << " ok=" << ok << " updates=" << notifications - previousNotifications
        << " expected=" << expected << " notified=" << sentRect;
    failures += !ok;
    previousNotifications = notifications;
}
static void key(int key, Qt::KeyboardModifiers modifiers = Qt::NoModifier) {
    auto *focus = QApplication::focusWidget();
    QKeyEvent press(QEvent::KeyPress, key, modifiers);
    QKeyEvent release(QEvent::KeyRelease, key, modifiers);
    QApplication::sendEvent(focus, &press);
    QApplication::sendEvent(focus, &release);
}
static void runStep(int index) {
    if (index >= int(steps.size())) {
        qWarning() << "ACCEPT SUMMARY failures=" << failures;
        qApp->setProperty("imeAcceptanceFailures", failures);
        qApp->quit();
        return;
    }
    steps[index]();
    QTimer::singleShot(300, qApp, [index] { runStep(index + 1); });
}
int QCoreApplication::exec() {
    using Exec = int (*)();
    auto original = reinterpret_cast<Exec>(dlsym(RTLD_NEXT, "_ZN16QCoreApplication4execEv"));
    QObject::connect(QGuiApplication::inputMethod(), &QInputMethod::cursorRectangleChanged, qApp, [] {
        ++notifications;
        sentWindow = QGuiApplication::focusWindow();
        sentRect = currentGlobalRect();
        qWarning() << "ACCEPT_NOTIFY" << notifications << sentRect;
    });
    QTimer::singleShot(1200, qApp, [] {
        editor = findEditor("muffin::EditorView");
        if (!editor) { qWarning() << "ACCEPT no editor"; qApp->setProperty("imeAcceptanceFailures", 1); qApp->quit(); return; }
        window = editor->window();
        window->resize(1000, 700);
        window->activateWindow();
        editor->setFocus();
        steps = {
            [] {
                auto *area = qobject_cast<QAbstractScrollArea *>(editor);
                QPointF p(area->viewport()->width()/2., 50.);
                QPointF global = area->viewport()->mapToGlobal(p.toPoint());
                QMouseEvent press(QEvent::MouseButtonPress, p, global, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
                QMouseEvent release(QEvent::MouseButtonRelease, p, global, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                QApplication::sendEvent(area->viewport(), &press);
                QApplication::sendEvent(area->viewport(), &release);
            },
            [] { check("normal"); for (int n=0; n<10; ++n) key(Qt::Key_Right); },
            [] { check("cursor-right"); key(Qt::Key_Down); key(Qt::Key_Down); },
            [] { check("cursor-down"); qobject_cast<QAbstractScrollArea *>(editor)->verticalScrollBar()->setValue(16); },
            [] { check("scroll"); window->move(300, 180); },
            [] { check("window-move"); window->showMaximized(); },
            [] { check("maximized"); window->showFullScreen(); },
            [] { check("fullscreen"); key(Qt::Key_Right); key(Qt::Key_Right); },
            [] {
                check("fullscreen-cursor");
                QInputMethodEvent event(QStringLiteral("nihao"), {{QInputMethodEvent::Cursor, 5, 1, {}}});
                QApplication::sendEvent(editor, &event);
            },
            [] {
                check("preedit");
                QInputMethodEvent cancel;
                QApplication::sendEvent(editor, &cancel);
            },
            [] {
                check("preedit-cancel");
                for (auto *action : window->findChildren<QAction *>())
                    if (action->shortcut() == QKeySequence(QStringLiteral("Ctrl+/"))) { action->trigger(); break; }
            },
            [] {
                editor = findEditor("muffin::VirtualSourceEdit");
                if (!editor) { qWarning() << "ACCEPT no source editor"; ++failures; return; }
                editor->setFocus();
            },
            [] { check("source-focus"); key(Qt::Key_Right); key(Qt::Key_Right); },
            [] { check("source-cursor"); key(Qt::Key_Down); },
            [] { check("source-down"); qobject_cast<QAbstractScrollArea *>(editor)->verticalScrollBar()->setValue(10); },
            [] { check("source-scroll"); previousNotifications = notifications; editor->update(); },
            [] {
                const bool unchanged = notifications == previousNotifications;
                check("idle-no-duplicate", false);
                if (!unchanged) { qWarning() << "ACCEPT redundant updates"; ++failures; }
            },
        };
        runStep(0);
    });
    const int result = original();
    return qApp->property("imeAcceptanceFailures").toInt() ? 1 : result;
}
