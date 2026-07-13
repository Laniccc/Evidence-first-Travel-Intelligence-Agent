package com.travel.intelligence.api.user.application;

import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import com.travel.intelligence.api.user.domain.UserAccount;
import com.travel.intelligence.api.user.domain.UserPrincipal;
import com.travel.intelligence.api.user.domain.UserRole;
import com.travel.intelligence.api.user.web.dto.AuthResponse;
import com.travel.intelligence.api.user.web.dto.LoginRequest;
import com.travel.intelligence.api.user.web.dto.RegisterRequest;
import com.travel.intelligence.api.user.web.dto.UserSummary;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {

    private final UserAccountStore users;
    private final PasswordHasher passwordHasher;
    private final AuthTokenIssuer tokenIssuer;

    public AuthService(UserAccountStore users, PasswordHasher passwordHasher, AuthTokenIssuer tokenIssuer) {
        this.users = users;
        this.passwordHasher = passwordHasher;
        this.tokenIssuer = tokenIssuer;
    }

    @Transactional
    public AuthResponse register(RegisterRequest request) {
        String username = normalizeUsername(request.username());
        String email = request.email().trim().toLowerCase(Locale.ROOT);
        if (users.existsByUsername(username)) {
            throw new ApiException(ApplicationErrorCode.USERNAME_EXISTS, "Username already exists");
        }
        if (users.existsByEmail(email)) {
            throw new ApiException(ApplicationErrorCode.EMAIL_EXISTS, "Email already exists");
        }
        String displayName = request.displayName() != null && !request.displayName().isBlank()
                ? request.displayName().trim()
                : username;
        UserAccount account = users.save(new UserAccount(
                username,
                email,
                passwordHasher.hash(request.password()),
                displayName,
                UserRole.USER));
        return new AuthResponse(tokenIssuer.createToken(account), UserSummary.from(account));
    }

    public AuthResponse login(LoginRequest request) {
        String identity = request.usernameOrEmail().trim();
        UserAccount account = users.findByUsername(normalizeUsername(identity))
                .or(() -> users.findByEmail(identity.toLowerCase(Locale.ROOT)))
                .orElseThrow(() -> new ApiException(ApplicationErrorCode.BAD_CREDENTIALS, "Invalid username or password"));
        if (!passwordHasher.matches(request.password(), account.getPasswordHash())) {
            throw new ApiException(ApplicationErrorCode.BAD_CREDENTIALS, "Invalid username or password");
        }
        return new AuthResponse(tokenIssuer.createToken(account), UserSummary.from(account));
    }

    public UserSummary me(UserPrincipal principal) {
        return users.findById(principal.id()).map(UserSummary::from)
                .orElseThrow(() -> new ApiException(ApplicationErrorCode.USER_NOT_FOUND, "User not found"));
    }

    private String normalizeUsername(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
