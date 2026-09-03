#ifndef IDISPLAY_CONTRIBUTOR_H
#define IDISPLAY_CONTRIBUTOR_H

#include <U8g2lib.h>

// Capability interface for plugins that render display pages.
class IDisplayContributor
{
    public:
        virtual ~IDisplayContributor() = default;

        virtual int getDisplayPageCount() const = 0;
        virtual int getCurrentDisplayPage() const { return 0; }
        virtual int renderDisplayPage(U8G2& u8g2, int page, int width, int height) const = 0;
};

#endif
