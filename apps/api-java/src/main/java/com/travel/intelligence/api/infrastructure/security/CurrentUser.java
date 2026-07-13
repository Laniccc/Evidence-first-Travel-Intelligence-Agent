package com.travel.intelligence.api.infrastructure.security;

import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import com.travel.intelligence.api.user.domain.UserPrincipal;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class CurrentUser {

    public UserPrincipal require(Authentication authentication) {
        if (authentication == null || !(authentication.getPrincipal() instanceof UserPrincipal principal)) {
            throw new ApiException(ApplicationErrorCode.UNAUTHORIZED, "Login required");
        }
        return principal;
    }
}
