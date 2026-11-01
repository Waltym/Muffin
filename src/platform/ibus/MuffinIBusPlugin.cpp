// SPDX-License-Identifier: MIT
#include "MuffinImePositionTracker.h"

#include <QLibraryInfo>
#include <QPluginLoader>
#include <qpa/qplatforminputcontext.h>
#include <qpa/qplatforminputcontextplugin_p.h>

// Load Qt's unmodified IBus implementation from a subdirectory so that the
// factory scanner sees only this shim for the "ibus" key. Returning the native
// context preserves its entire keyboard/composition/candidate protocol.
class MuffinIBusPlugin final : public QPlatformInputContextPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QPlatformInputContextFactoryInterface_iid FILE "muffin-ibus.json")

public:
    QPlatformInputContext *create(const QString &key, const QStringList &parameters) override {
        if (key.compare(QStringLiteral("ibus"), Qt::CaseInsensitive) != 0)
            return nullptr;
        const QString originalPath = QLibraryInfo::path(QLibraryInfo::PluginsPath) +
            QStringLiteral("/platforminputcontexts/upstream/libibusplatforminputcontextplugin.so");
        auto *loader = new QPluginLoader(originalPath);
        loader->setLoadHints(QLibrary::PreventUnloadHint | QLibrary::ResolveAllSymbolsHint);
        auto *factory = qobject_cast<QPlatformInputContextPlugin *>(loader->instance());
        if (!factory) {
            qWarning("Muffin IBus: native plugin could not be loaded: %s", qPrintable(loader->errorString()));
            delete loader;
            return nullptr;
        }
        auto *context = factory->create(QStringLiteral("ibus"), parameters);
        if (!context) {
            delete loader;
            return nullptr;
        }
        loader->setParent(context);
        new MuffinImePositionTracker(context);
        return context;
    }
};

#include "MuffinIBusPlugin.moc"
