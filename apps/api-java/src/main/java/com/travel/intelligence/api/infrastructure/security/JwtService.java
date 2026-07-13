package com.travel.intelligence.api.infrastructure.security;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import com.travel.intelligence.api.user.domain.UserAccount;
import com.travel.intelligence.api.user.domain.UserPrincipal;
import com.travel.intelligence.api.user.domain.UserRole;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Service;

@Service
public class JwtService {

    private static final Base64.Encoder URL_ENCODER = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder URL_DECODER = Base64.getUrlDecoder();

    private final JwtProperties properties;
    private final ObjectMapper objectMapper;

    public JwtService(JwtProperties properties, ObjectMapper objectMapper) {
        this.properties = properties;
        this.objectMapper = objectMapper;
    }

    public String createToken(UserAccount account) {
        Instant now = Instant.now();
        long ttlSeconds = Math.max(1, properties.ttlMinutes()) * 60;
        Map<String, Object> header = Map.of("alg", "HS256", "typ", "JWT");
        Map<String, Object> payload = Map.of(
                "sub", account.getId(),
                "username", account.getUsername(),
                "displayName", account.getDisplayName(),
                "role", account.getRole().name(),
                "iat", now.getEpochSecond(),
                "exp", now.plusSeconds(ttlSeconds).getEpochSecond());
        String unsigned = encodeJson(header) + "." + encodeJson(payload);
        return unsigned + "." + sign(unsigned);
    }

    public UserPrincipal parseToken(String token) {
        String[] parts = token != null ? token.split("\\.") : new String[0];
        if (parts.length != 3) {
            throw unauthorized("Invalid token");
        }
        String unsigned = parts[0] + "." + parts[1];
        if (!MessageDigest.isEqual(sign(unsigned).getBytes(StandardCharsets.UTF_8), parts[2].getBytes(StandardCharsets.UTF_8))) {
            throw unauthorized("Invalid token signature");
        }
        Map<?, ?> payload = decodeJson(parts[1]);
        long exp = longClaim(payload.get("exp"));
        if (Instant.now().getEpochSecond() > exp) {
            throw unauthorized("Token expired");
        }
        Long userId = longClaim(payload.get("sub"));
        String username = stringClaim(payload.get("username"));
        String displayName = stringClaim(payload.get("displayName"));
        UserRole role = UserRole.valueOf(stringClaim(payload.get("role")));
        return new UserPrincipal(userId, username, displayName, role);
    }

    private String encodeJson(Map<String, Object> value) {
        try {
            return URL_ENCODER.encodeToString(objectMapper.writeValueAsBytes(value));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Failed to encode token", ex);
        }
    }

    private Map<?, ?> decodeJson(String value) {
        try {
            return objectMapper.readValue(URL_DECODER.decode(value), Map.class);
        } catch (Exception ex) {
            throw unauthorized("Invalid token payload");
        }
    }

    private String sign(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(properties.secret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return URL_ENCODER.encodeToString(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("Failed to sign token", ex);
        }
    }

    private static long longClaim(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String text) {
            return Long.parseLong(text);
        }
        throw unauthorized("Invalid token claim");
    }

    private static String stringClaim(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text;
        }
        throw unauthorized("Invalid token claim");
    }

    private static ApiException unauthorized(String message) {
        return new ApiException(ApplicationErrorCode.UNAUTHORIZED, message);
    }
}
