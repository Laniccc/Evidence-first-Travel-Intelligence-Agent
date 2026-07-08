package com.travel.intelligence.api.tool;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@ConfigurationProperties(prefix = "tool-gateway")
public class ToolGatewayProperties {

    private boolean enabled = true;
    private boolean mcpEnabled = false;
    private int mcpTimeoutSeconds = 30;

    @NestedConfigurationProperty
    private SearchMcp search = new SearchMcp();

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isMcpEnabled() {
        return mcpEnabled;
    }

    public void setMcpEnabled(boolean mcpEnabled) {
        this.mcpEnabled = mcpEnabled;
    }

    public int getMcpTimeoutSeconds() {
        return mcpTimeoutSeconds;
    }

    public void setMcpTimeoutSeconds(int mcpTimeoutSeconds) {
        this.mcpTimeoutSeconds = mcpTimeoutSeconds;
    }

    public SearchMcp getSearch() {
        return search;
    }

    public void setSearch(SearchMcp search) {
        this.search = search;
    }

    public static class SearchMcp {
        private boolean enabled = false;
        private String serverUrl = "";
        private String toolName = "public_web_search";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getServerUrl() {
            return serverUrl;
        }

        public void setServerUrl(String serverUrl) {
            this.serverUrl = serverUrl;
        }

        public String getToolName() {
            return toolName;
        }

        public void setToolName(String toolName) {
            this.toolName = toolName;
        }
    }
}
