// Inspect/edit only an isolated temporary document, never the user's profile.
#include "editor/EditorView.h"
#include "render/InlineLayout.h"
#include <QApplication>
#include <QAction>
#include <QCheckBox>
#include <QDialog>
#include <QDir>
#include <QInputMethodEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QSettings>
#include <QTimer>
#include <dlfcn.h>

static muffin::EditorView *view = nullptr;
static void dump(const char *stage) {
    QSet<muffin::NodeId> seen;
    qWarning() << "EXT_STAGE" << stage << "highlightColor=" << view->theme().highlightBackgroundColor();
    if (auto style = view->theme().elementStyle(QStringLiteral("mark")))
        qWarning() << "EXT_MARK_STYLE" << style->paint.backgroundColor;
    for (int y = 10; y < qMin(450, view->viewport()->height()); y += 5) {
        const auto hit = view->hitTest(QPointF(view->viewport()->width()/2., y));
        if (!hit.blockId.isValid() || seen.contains(hit.blockId)) continue;
        seen.insert(hit.blockId);
        const auto *block = view->blockLayoutForNode(hit.blockId);
        const auto *layout = block ? block->inlineLayout() : nullptr;
        if (!layout) continue;
        qWarning() << "EXT_BLOCK" << hit.blockId.toString() << "display=" << layout->displayText()
            << "visible=" << layout->visibleText();
        for (const auto &box : layout->inlineBoxes())
            qWarning() << "EXT_BOX" << box.hostKey << box.style.paint.backgroundColor << box.borderBox;
        for (const auto &format : layout->debugTextFormats(view->theme(), view->theme().paragraphFont())) {
            if (format.format.baselineOffset() || format.format.background().style() != Qt::NoBrush)
                qWarning() << "EXT_FORMAT" << format.start << format.length
                    << "baseline=" << format.format.baselineOffset()
                    << "background=" << format.format.background().color();
        }
    }
    const QString directory = qEnvironmentVariable("MUFFIN_EXTENSION_PROBE_OUT");
    QImage image = view->viewport()->grab().toImage();
    if (image.width() > 1600 || image.height() > 1600)
        image = image.scaled(1600, 1600, Qt::KeepAspectRatio, Qt::SmoothTransformation);
    image.save(directory + QLatin1Char('/') + QString::fromLatin1(stage) + QStringLiteral(".png"));
}
int QCoreApplication::exec() {
    using Exec = int (*)();
    auto original = reinterpret_cast<Exec>(dlsym(RTLD_NEXT, "_ZN16QCoreApplication4execEv"));
    QTimer::singleShot(1600, qApp, [] {
        qWarning() << "EXT_SETTINGS" << QSettings().value("markdown/highlight")
            << QSettings().value("markdown/subscript") << QSettings().value("markdown/superscript");
        for (auto *widget : QApplication::allWidgets())
            if (auto *candidate = qobject_cast<muffin::EditorView *>(widget); candidate && candidate->isVisible()) {
                view = candidate; break;
            }
        if (!view) { qWarning() << "EXT_NO_EDITOR"; qApp->quit(); return; }
        view->window()->resize(1100, 700);
        QTimer::singleShot(300, qApp, [] {
            dump("initial");
            QKeyEvent end(QEvent::KeyPress, Qt::Key_End, Qt::ControlModifier);
            QApplication::sendEvent(view, &end);
            QTimer::singleShot(300, qApp, [] {
                dump("cursor-away");
                if (!qEnvironmentVariableIsSet("MUFFIN_EXTENSION_LIVE_TEST")) { qApp->exit(0); return; }
                QTimer::singleShot(300, qApp, [] {
                    auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
                    if (!dialog) { qWarning() << "EXT_NO_PREFS"; qApp->exit(1); return; }
                    int changed = 0;
                    for (auto *box : dialog->findChildren<QCheckBox *>())
                        if (box->text().contains(QStringLiteral("H~2~O")) ||
                            box->text().contains(QStringLiteral("X^2^")) ||
                            box->text().contains(QStringLiteral("==key=="))) {
                            box->setChecked(true);
                            ++changed;
                        }
                    qWarning() << "EXT_PREFS_ENABLED" << changed;
                    dialog->accept();
                });
                for (auto *action : view->window()->findChildren<QAction *>())
                    if (action->shortcut() == QKeySequence(QStringLiteral("Ctrl+,"))) { action->trigger(); break; }
                QTimer::singleShot(350, qApp, [] {
                    dump("after-preferences");
                    view->setFocus();
                    // Place a real editor selection via its mouse handling;
                    // a freshly opened document need not have an active caret.
                    for (int y = 10; y < view->viewport()->height(); y += 5) {
                        const QPointF p(view->viewport()->width()/2., y);
                        auto hit = view->hitTest(p);
                        auto *block = hit.blockId.isValid() ? view->blockLayoutForNode(hit.blockId) : nullptr;
                        if (!block || !block->inlineLayout() || block->inlineLayout()->visibleText() != QStringLiteral("End of test")) continue;
                        const QPointF global = view->viewport()->mapToGlobal(p.toPoint());
                        QMouseEvent press(QEvent::MouseButtonPress, p, global, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
                        QMouseEvent release(QEvent::MouseButtonRelease, p, global, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                        QApplication::sendEvent(view->viewport(), &press);
                        QApplication::sendEvent(view->viewport(), &release);
                        break;
                    }
                    QInputMethodEvent commit;
                    commit.setCommitString(QStringLiteral(" H~2~O X^2^ ==typed=="));
                    QApplication::sendEvent(view, &commit);
                    QTimer::singleShot(350, qApp, [] {
                        dump("incremental-input");
                        qApp->exit(0);
                    });
                });
            });
        });
    });
    return original();
}
