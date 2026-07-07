package com.deepresearch.api.user;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @PostMapping("/register")
    public ResponseEntity<?> register(@RequestBody UserService.RegisterRequest req) {
        try {
            var result = userService.register(req);
            return ResponseEntity.ok(Map.of(
                "token", result.token(),
                "userId", result.userId(),
                "username", result.username()
            ));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest().body(Map.of("error", e.getMessage()));
        }
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody UserService.LoginRequest req) {
        try {
            var result = userService.login(req);
            return ResponseEntity.ok(Map.of(
                "token", result.token(),
                "userId", result.userId(),
                "username", result.username()
            ));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.status(401).body(Map.of("error", e.getMessage()));
        }
    }
}
