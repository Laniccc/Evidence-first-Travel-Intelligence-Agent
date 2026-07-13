package com.travel.intelligence.api.infrastructure.security;

import com.travel.intelligence.api.user.application.AuthTokenIssuer;
import com.travel.intelligence.api.user.domain.UserAccount;
import org.springframework.stereotype.Component;

@Component
public class JwtAuthTokenIssuer implements AuthTokenIssuer {

    private final JwtService jwtService;

    public JwtAuthTokenIssuer(JwtService jwtService) {
        this.jwtService = jwtService;
    }

    @Override
    public String createToken(UserAccount account) {
        return jwtService.createToken(account);
    }
}
