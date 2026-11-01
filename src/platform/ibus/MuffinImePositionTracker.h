// SPDX-License-Identifier: MIT
#pragma once

#include <QApplication>
#include <QEvent>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QPointer>
#include <QTimer>
#include <QWidget>
#include <QWindow>

// Compatibility fix for the stock Muffin 0.7.9 editor: it implements cursor
// queries but does not notify QInputMethod when its painted caret moves. This
// observer never filters keys, changes text, or changes the input transform.
// Query after layout/paint, coalesce updates, and notify only on real geometry
// changes (or focus/composition changes). No polling and no global settings.
class MuffinImePositionTracker final : public QObject {
public:
    explicit MuffinImePositionTracker(QObject *parent = nullptr) : QObject(parent) {
        timer_.setSingleShot(true);
        timer_.setInterval(0);
        connect(&timer_, &QTimer::timeout, this, [this] { synchronize(); });
        auto *app = qobject_cast<QGuiApplication *>(QCoreApplication::instance());
        if (app) {
            app->installEventFilter(this);
            connect(app, &QGuiApplication::focusObjectChanged, this, [this] {
                lastFocus_.clear();
                schedule(true);
            });
        }
        schedule(true);
    }

protected:
    bool eventFilter(QObject *watched, QEvent *event) override {
        // All widgets in the editor's window are relevant: the caret can move
        // when a sibling sidebar resizes even if no key event is delivered.
        auto *focus = trackedFocus();
        if (!focus)
            return false;
        auto *widget = qobject_cast<QWidget *>(watched);
        if ((!widget || widget->window() != focus->window()) && watched != focus->window()->windowHandle())
            return false;
        switch (event->type()) {
        case QEvent::InputMethod:
        case QEvent::FocusIn:
            schedule(true);
            break;
        case QEvent::KeyPress:
        case QEvent::MouseButtonRelease:
        case QEvent::Wheel:
        case QEvent::Resize:
        case QEvent::Move:
        case QEvent::LayoutRequest:
        case QEvent::Show:
        case QEvent::Paint:
        case QEvent::WindowStateChange:
        case QEvent::ScreenChangeInternal:
        case QEvent::DevicePixelRatioChange:
            schedule(false);
            break;
        default:
            break;
        }
        return false; // Native IBus and the editor retain all input handling.
    }

private:
    static QWidget *trackedFocus() {
        // The plugin is created during QGuiApplication initialization, before
        // QApplication's constructor has completed. Do not query widgets then.
        if (!qobject_cast<QApplication *>(QCoreApplication::instance()))
            return nullptr;
        QWidget *focus = QApplication::focusWidget();
        if (!focus)
            return nullptr;
        const QByteArray name(focus->metaObject()->className());
        return name == "muffin::EditorView" || name == "muffin::VirtualSourceEdit" ? focus : nullptr;
    }

    void schedule(bool force) {
        force_ = force_ || force;
        if (!timer_.isActive())
            timer_.start();
    }

    void synchronize() {
        const bool force = force_;
        force_ = false;
        QWidget *focus = trackedFocus();
        QWindow *window = QGuiApplication::focusWindow();
        if (!focus || !window || focus->window()->windowHandle() != window)
            return;
        QInputMethodQueryEvent enabled(Qt::ImEnabled);
        QCoreApplication::sendEvent(focus, &enabled);
        if (!enabled.value(Qt::ImEnabled).toBool())
            return;
        QInputMethod *input = QGuiApplication::inputMethod();
        const QRectF rect = input->cursorRectangle();
        if (!rect.isValid())
            return; // Never replace a valid anchor with QWidget's bottom edge.
        const QRectF globalRect = rect.translated(window->mapToGlobal(QPoint()));
        const qreal scale = window->devicePixelRatio();
        if (!force && focus == lastFocus_ && window == lastWindow_ && rect == lastRect_ &&
            globalRect == lastGlobalRect_ && qFuzzyCompare(scale, lastScale_))
            return;
        lastFocus_ = focus;
        lastWindow_ = window;
        lastRect_ = rect;
        lastGlobalRect_ = globalRect;
        lastScale_ = scale;
        // This emits cursorRectangleChanged, which Qt's unchanged IBus context
        // connects to SetCursorLocation. Qt retains all screen/DPI conversion.
        input->update(Qt::ImCursorRectangle);
    }

    QTimer timer_;
    bool force_ = false;
    QPointer<QWidget> lastFocus_;
    QPointer<QWindow> lastWindow_;
    QRectF lastRect_;
    QRectF lastGlobalRect_;
    qreal lastScale_ = 1;
};
