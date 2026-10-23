#include <gtest/gtest.h>
#include "IPlugin.h"
#include "PluginRegistry.h"

// Minimal concrete plugin for testing
class FakePlugin : public IPlugin {
    const char* _id;
    const char* _name;
public:
    FakePlugin(const char* id, const char* name) : _id(id), _name(name) {}

    const char* getId() const override { return _id; }
    const char* getName() const override { return _name; }

    void setup(HAL*, Storage*, Logger*, LedController*) override {}
    void loop() override {}

    void getParameterDefs(std::vector<ParameterDef>&) const override {}

    void getStats(std::vector<StatEntry>&) const override {}
};

class PluginRegistryTest : public ::testing::Test {
protected:
    PluginRegistry registry;
    FakePlugin pluginA{"plugin_a", "Plugin A"};
    FakePlugin pluginB{"plugin_b", "Plugin B"};
    FakePlugin pluginC{"plugin_c", "Plugin C"};
};

TEST_F(PluginRegistryTest, EmptyRegistryCountIsZero)
{
    EXPECT_EQ(registry.getAll().size(), 0u);
}

TEST_F(PluginRegistryTest, AddIncrementsCount)
{
    registry.add(&pluginA);
    EXPECT_EQ(registry.getAll().size(), 1u);
    registry.add(&pluginB);
    EXPECT_EQ(registry.getAll().size(), 2u);
}

TEST_F(PluginRegistryTest, GetByIdFindsPlugin)
{
    registry.add(&pluginA);
    registry.add(&pluginB);

    IPlugin* found = registry.get("plugin_b");
    ASSERT_NE(found, nullptr);
    EXPECT_STREQ(found->getId(), "plugin_b");
    EXPECT_STREQ(found->getName(), "Plugin B");
}

TEST_F(PluginRegistryTest, GetByIdReturnsNullForMissing)
{
    registry.add(&pluginA);
    EXPECT_EQ(registry.get("nonexistent"), nullptr);
}

TEST_F(PluginRegistryTest, GetAllReturnsAllPlugins)
{
    registry.add(&pluginA);
    registry.add(&pluginB);
    registry.add(&pluginC);

    const auto& all = registry.getAll();
    EXPECT_EQ(all.size(), 3u);
    EXPECT_STREQ(all[0]->getId(), "plugin_a");
    EXPECT_STREQ(all[1]->getId(), "plugin_b");
    EXPECT_STREQ(all[2]->getId(), "plugin_c");
}
