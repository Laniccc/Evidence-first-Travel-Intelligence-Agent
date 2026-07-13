package com.travel.intelligence.api.user.application;

import com.travel.intelligence.api.user.domain.UserAccount;

public interface AuthTokenIssuer {

    String createToken(UserAccount account);
}
