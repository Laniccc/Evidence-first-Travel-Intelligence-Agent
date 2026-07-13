package com.travel.intelligence.api.user.web;

import com.travel.intelligence.api.infrastructure.security.CurrentUser;
import com.travel.intelligence.api.user.application.AuthService;
import com.travel.intelligence.api.user.web.dto.AuthResponse;
import com.travel.intelligence.api.user.web.dto.LoginRequest;
import com.travel.intelligence.api.user.web.dto.RegisterRequest;
import com.travel.intelligence.api.user.web.dto.UserSummary;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final CurrentUser currentUser;

    public AuthController(AuthService authService, CurrentUser currentUser) {
        this.authService = authService;
        this.currentUser = currentUser;
    }

    @PostMapping("/register")
    public AuthResponse register(@Valid @RequestBody RegisterRequest request) {
        return authService.register(request);
    }

    @PostMapping("/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request);
    }

    @GetMapping("/me")
    public UserSummary me(Authentication authentication) {
        return authService.me(currentUser.require(authentication));
    }
}
